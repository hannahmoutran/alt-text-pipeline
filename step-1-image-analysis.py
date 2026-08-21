#!/usr/bin/env python3
"""
Alt Text Pipeline — Step 1: Image Analysis

Processes all images in a collection and generates alt text using Claude, OpenAI, or Gemini.

If collection-examples.txt exists in the image folder (written by the grounding workflow),
the pipeline will:
  1. Analyze the archivist's corrections to generate a collection-specific style guide
  2. Use that style guide and the grounding examples in the prompt for every image

Usage (standalone):
    python step-1-image-analysis.py

Usage (via run.py):
    python run.py
"""

import os
import sys
import json
import logging
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config import get_step1_config, STEP1_PROMPT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
for lib in ("anthropic", "openai", "google", "urllib3", "httpx", "portkey_ai"):
    logging.getLogger(lib).setLevel(logging.WARNING)

from pipeline_core import (
    load_collection_context, collect_all_images, init_client, process_image_list,
    read_examples_file, format_examples_for_prompt, generate_style_analysis,
    load_style_guide,
)


def main():
    cfg = get_step1_config()
    provider: str = os.getenv('CONFIG_PROVIDER') or cfg['provider']
    model_name: str = os.getenv('CONFIG_MODEL') or cfg['model']
    input_folder_name: str = os.getenv('CONFIG_IMAGE_FOLDER') or cfg['image_folder']
    use_portkey: bool = os.getenv('CONFIG_USE_PORTKEY', '').lower() == 'true' or cfg.get('use_portkey', False)
    images_per_call: int = int(os.getenv('CONFIG_IMAGES_PER_CALL') or cfg.get('images_per_call', 1))

    input_folder = os.path.join(script_dir, input_folder_name)
    if not os.path.exists(input_folder):
        print(f"Input folder not found: {input_folder}")
        return 1

    collection_context = load_collection_context(input_folder)

    print(f"\nIMAGE ALT TEXT GENERATION — Step 1")
    print(f"Provider : {provider.upper()}" + (" (via Portkey)" if use_portkey else ""))
    print(f"Model    : {model_name}")
    print(f"Folder   : {input_folder_name}")
    if images_per_call > 1:
        print(f"Batch    : {images_per_call} images per call")
    if collection_context:
        print(f"Context  : collection-context.txt loaded")

    client = init_client(provider, use_portkey)

    all_images = collect_all_images(input_folder)
    total = len(all_images)
    if total == 0:
        print(f"No images found in {input_folder}")
        return 1
    print(f"\nFound {total} image(s) to process")

    examples = read_examples_file(input_folder)
    style_analysis = load_style_guide(input_folder)

    if examples and not style_analysis:
        # Fallback: generate inline if no pre-generated guide exists (e.g. grounding
        # workflow was skipped or run before this change was made).
        print(f"\nFound {len(examples)} grounding example(s) — generating style analysis...")
        style_analysis = generate_style_analysis(examples, provider, client, model_name)
        if style_analysis:
            print(f"\n{style_analysis}\n")
        else:
            print("Style analysis unavailable — proceeding with examples only.")
    elif style_analysis:
        print(f"\nLoaded style guide from collection-style-guide.txt")

    collection_examples = format_examples_for_prompt(examples, style_analysis)
    prompt = STEP1_PROMPT.format(
        collection_context=collection_context,
        collection_examples=collection_examples,
    )
    print()

    timestamp = datetime.now().strftime("%Y-%m-%d_Time_%H-%M-%S")
    folder_slug = input_folder_name.replace(os.sep, "-").replace("/", "-")
    output_folder_name = f"AltText_{folder_slug}_{model_name}_{timestamp}"
    output_dir = os.path.join(script_dir, "output_folders", output_folder_name)
    os.makedirs(os.path.join(output_dir, "metadata", "json"), exist_ok=True)

    script_start = time.time()
    all_results, issues, total_input_tokens, total_output_tokens = process_image_list(
        all_images, prompt, provider, client, model_name, images_per_call, total, 0
    )
    total_time = time.time() - script_start

    summary = {
        "provider": provider,
        "model": model_name,
        "use_portkey": use_portkey,
        "image_folder": input_folder_name,
        "total_images": total,
        "successful": total - len(issues),
        "failed": len(issues),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_time_seconds": round(total_time, 2),
    }
    if issues:
        summary["issues"] = issues
    if examples:
        summary["grounding_examples_used"] = len(examples)
    if style_analysis:
        summary["style_analysis"] = style_analysis

    output = {"summary": summary, "results": all_results}
    json_path = os.path.join(output_dir, "metadata", "json", "alt_text_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSTEP 1 COMPLETE")
    print(f"Processed : {total - len(issues)}/{total} images")
    if issues:
        print(f"Failed    : {len(issues)}")
    print(f"Tokens    : {total_input_tokens + total_output_tokens:,}  (in: {total_input_tokens:,}, out: {total_output_tokens:,})")
    print(f"Time      : {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"Output    : output_folders/{output_folder_name}/metadata/json/alt_text_results.json")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
