#!/usr/bin/env python3
"""
Alt Text Pipeline — Step 0: Create Grounding Examples

Processes a small sample of images without any prior examples,
creating a baseline the archivist can review and correct.
Those corrected examples then guide the full image analysis run,
and the AI will derive a style guide from the archivist's edits.

Workflow:
  1. python step-0-grounding.py                            # process N sample images
  2. python step-2-html-review.py                          # open in browser, edit alt text
  3. [in browser] Export Decisions → move JSON to review/exports/
  4. python integrate_edits.py --export-grounding          # write collection-examples.txt
  5. python run.py                                         # full run with style-guided examples

Usage:
    python step-0-grounding.py
    python step-0-grounding.py --count 10
    python step-0-grounding.py --folder images/my-collection --count 15
"""

import os
import sys
import json
import argparse
import logging
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
for lib in ("anthropic", "openai", "google", "urllib3", "httpx", "portkey_ai"):
    logging.getLogger(lib).setLevel(logging.WARNING)

from config import get_step1_config, STEP1_PROMPT, GROUNDING_COUNT
from pipeline_core import load_collection_context, collect_all_images, init_client, process_image_list


def main():
    parser = argparse.ArgumentParser(
        description='Process a sample of images to create grounding examples for a collection.'
    )
    parser.add_argument('--count', '-n', type=int, default=None,
        help='Number of sample images to process (default: GROUNDING_COUNT from config.py)')
    parser.add_argument('--folder', '-f', default=None,
        help='Image folder path (default: IMAGE_FOLDER from config.py)')
    args = parser.parse_args()

    cfg = get_step1_config(args.folder)
    provider = cfg['provider']
    model_name = cfg['model']
    input_folder_name = args.folder or cfg['image_folder']
    use_portkey = cfg.get('use_portkey', False)
    images_per_call = cfg.get('images_per_call', 1)
    count = args.count if args.count is not None else GROUNDING_COUNT

    input_folder = os.path.join(script_dir, input_folder_name)
    if not os.path.exists(input_folder):
        print(f"Input folder not found: {input_folder}")
        return 1

    collection_context = load_collection_context(input_folder)

    print(f"\nGROUNDING — Step 0: Sample Image Analysis")
    print(f"Provider : {provider.upper()}" + (" (via Portkey)" if use_portkey else ""))
    print(f"Model    : {model_name}")
    print(f"Folder   : {input_folder_name}")
    print(f"Sample   : first {count} images")
    if collection_context:
        print(f"Context  : collection-context.txt loaded")

    client = init_client(provider, use_portkey)
    all_images = collect_all_images(input_folder)
    total_in_folder = len(all_images)

    if total_in_folder == 0:
        print(f"\nNo images found in {input_folder}")
        return 1

    sample_images = all_images[:count]
    actual_count = len(sample_images)
    print(f"\nFound {total_in_folder} image(s) total — processing first {actual_count}\n")

    prompt = STEP1_PROMPT.format(collection_context=collection_context, collection_examples="")

    timestamp = datetime.now().strftime("%Y-%m-%d_Time_%H-%M-%S")
    folder_slug = input_folder_name.replace(os.sep, "-").replace("/", "-")
    output_folder_name = f"AltText_{folder_slug}_grounding_{model_name}_{timestamp}"
    output_dir = os.path.join(script_dir, "output_folders", output_folder_name)
    os.makedirs(os.path.join(output_dir, "metadata", "json"), exist_ok=True)

    script_start = time.time()
    results, issues, total_in_tokens, total_out_tokens = process_image_list(
        sample_images, prompt, provider, client, model_name, images_per_call, actual_count, 0
    )
    total_time = time.time() - script_start

    summary = {
        "provider": provider,
        "model": model_name,
        "use_portkey": use_portkey,
        "image_folder": input_folder_name,
        "grounding_run": True,
        "total_images": actual_count,
        "successful": actual_count - len(issues),
        "failed": len(issues),
        "total_input_tokens": total_in_tokens,
        "total_output_tokens": total_out_tokens,
        "total_tokens": total_in_tokens + total_out_tokens,
        "total_time_seconds": round(total_time, 2),
    }
    if issues:
        summary["issues"] = issues

    output = {"summary": summary, "results": results}
    json_path = os.path.join(output_dir, "metadata", "json", "alt_text_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nGROUNDING COMPLETE")
    print(f"Processed : {actual_count - len(issues)}/{actual_count} images")
    if issues:
        print(f"Failed    : {len(issues)}")
    print(f"Tokens    : {total_in_tokens + total_out_tokens:,}  (in: {total_in_tokens:,}, out: {total_out_tokens:,})")
    print(f"Time      : {total_time:.1f}s")
    print(f"Output    : output_folders/{output_folder_name}/")
    print(f"\n{'='*60}")
    print(f"NEXT STEPS")
    print(f"{'='*60}")
    print(f"  1. Create the HTML review interface:")
    print(f"       python step-2-html-review.py --folder output_folders/{output_folder_name}")
    print(f"     Review each image, edit the alt text as needed,")
    print(f"     then click 'Export Decisions' and save the JSON.")
    print(f"\n  2. Move the exported JSON into:")
    print(f"       output_folders/{output_folder_name}/review/exports/")
    print(f"\n  3. Write the grounding examples file:")
    print(f"       python integrate_edits.py --folder output_folders/{output_folder_name} --export-grounding")
    print(f"     This writes collection-examples.txt to: {input_folder_name}/")
    print(f"\n  4. Run the full image analysis:")
    print(f"       python run.py")
    print(f"     The AI will first analyze your edits to derive a collection style guide,")
    print(f"     then apply that style to every image in the collection.")
    print(f"{'='*60}")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
