#!/usr/bin/env python3
"""
Alt Text Pipeline — Step 0: Create Calibration Examples

Processes a small sample of images without any prior examples,
creating a baseline the archivist can review and correct.
Those corrected examples then guide the full image analysis run,
and the AI will derive a style guide from the archivist's edits.

Workflow:
  1. python step-0-calibration.py                            # process N sample images (set in config)
  2. python step-2-html-review.py                          # open in browser, edit alt text
  3. [in browser] Export Decisions → move JSON to review/exports/
  4. python step-0-calibration.py --export                   # write collection-examples.txt
  4b. python step-0-calibration.py --test                   # verify style guide on fresh images
  5. python run.py                                         # full run with style-guided examples

Usage:
    python step-0-calibration.py
    python step-0-calibration.py --folder images/my-collection
    python step-0-calibration.py --export          # integrate reviewed decisions → collection-examples.txt
    python step-0-calibration.py --export --folder output_folders/AltText_...
    python step-0-calibration.py --test                     # test on new images with collection-examples.txt
"""

import os
import sys
import json
import argparse
import logging
import subprocess
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
for lib in ("anthropic", "openai", "google", "urllib3", "httpx", "portkey_ai"):
    logging.getLogger(lib).setLevel(logging.WARNING)

from config import (
    get_step1_config, STEP1_PROMPT, CALIBRATION_COUNT, CALIBRATION_TEST_COUNT,
    CALIBRATION_TEST_SKIP_CALIBRATION, RUN_HTML_REVIEW, RELATIONSHIP_BETWEEN_IMAGES_PER_CALL,
)
from pipeline_core import (
    load_collection_context, collect_all_images, init_client, process_image_list,
    read_examples_file, format_examples_for_prompt, generate_style_analysis, load_style_guide,
    portkey_active,
)


def main():
    parser = argparse.ArgumentParser(
        description='Process a sample of images to create calibration examples for a collection.'
    )
    parser.add_argument('--folder', '-f', default=None,
        help='Image folder path (default: IMAGE_FOLDER from config.py). '
             'In --export mode: path to an AltText_ output folder.')
    parser.add_argument('--test', '-t', action='store_true',
        help='Test mode: run on fresh images using the existing collection-examples.txt to verify the style guide')
    parser.add_argument('--export', '-g', action='store_true',
        help='Integrate reviewer decisions and write collection-examples.txt to the image folder.')
    parser.add_argument('--decisions', '-d', default=None,
        help='Path to a specific decisions JSON file (used with --export).')
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # EXPORT-CALIBRATION MODE — integrate reviewer edits → collection-examples.txt
    # -------------------------------------------------------------------------
    if args.export:
        from integrate_edits import (
            AltTextEditsIntegrator,
            prompt_for_folder,
            prompt_for_decisions,
        )

        base_output_dir = os.path.join(script_dir, "output_folders")

        if args.folder:
            folder_path = args.folder
            if not os.path.isabs(folder_path):
                folder_path = os.path.join(script_dir, folder_path)
            if not os.path.isdir(folder_path):
                print(f"Error: folder not found: {folder_path}")
                return 1
            print(f"Using folder: {os.path.basename(folder_path)}")
        else:
            folder_path = prompt_for_folder(base_output_dir)
            if not folder_path:
                return 1
            print(f"Selected: {os.path.basename(folder_path)}")

        if args.decisions:
            decisions_path = args.decisions
            if not os.path.exists(decisions_path):
                print(f"Error: decisions file not found: {decisions_path}")
                return 1
            print(f"Using decisions: {os.path.basename(decisions_path)}")
        else:
            exports_folder = os.path.join(folder_path, "review", "exports")
            decisions_path = prompt_for_decisions(exports_folder)
            if not decisions_path:
                print("Operation cancelled.")
                return 0
            print(f"Selected: {os.path.basename(decisions_path)}")

        integrator = AltTextEditsIntegrator(folder_path)
        success = integrator.run(decisions_path=decisions_path, export_calibration=True)

        if success:
            print(f"\n{'='*60}")
            print(f"NEXT STEPS")
            print(f"{'='*60}")
            print(f"  Verify the style guide on fresh images:")
            print(f"    python step-0-calibration.py --test")
            print(f"{'='*60}")

        return 0 if success else 1

    cfg = get_step1_config(args.folder)
    provider = cfg['provider']
    model_name = cfg['model']
    input_folder_name = args.folder or cfg['image_folder']
    use_portkey = portkey_active(provider, cfg.get('use_portkey', False))
    images_per_call = cfg.get('images_per_call', 1)

    input_folder = os.path.join(script_dir, input_folder_name)
    if not os.path.exists(input_folder):
        print(f"Input folder not found: {input_folder}")
        return 1

    collection_context = load_collection_context(input_folder)
    client = init_client(provider, use_portkey)
    all_images = collect_all_images(input_folder)
    total_in_folder = len(all_images)

    if total_in_folder == 0:
        print(f"\nNo images found in {input_folder}")
        return 1

    # -------------------------------------------------------------------------
    # TEST MODE — verify style guide on fresh images
    # -------------------------------------------------------------------------
    if args.test:
        examples = read_examples_file(input_folder)
        if not examples:
            print(f"\nNo collection-examples.txt found in {input_folder_name}")
            print(f"Run the calibration workflow first:")
            print(f"  python integrate_edits.py --folder <calibration_output> --export")
            return 1

        style_analysis = load_style_guide(input_folder)
        if not style_analysis:
            print(f"\nGenerating style analysis from examples...")
            style_analysis = generate_style_analysis(examples, provider, client, model_name)
            if style_analysis:
                print(f"\n{style_analysis}\n")

        collection_examples = format_examples_for_prompt(examples, style_analysis)
        prompt = STEP1_PROMPT.format(
            collection_context=collection_context,
            collection_examples=collection_examples,
        )

        calibration_count = CALIBRATION_COUNT
        skip = calibration_count if CALIBRATION_TEST_SKIP_CALIBRATION else 0
        test_count = CALIBRATION_TEST_COUNT
        test_images = all_images[skip : skip + test_count]
        actual_count = len(test_images)

        if actual_count == 0:
            print(f"\nNo test images available after skipping {skip} calibration image(s).")
            print(f"Add more images to {input_folder_name} or set CALIBRATION_TEST_SKIP_CALIBRATION = False.")
            return 1

        print(f"\nCALIBRATION TEST — Step 0: Style Guide Verification")
        print(f"Provider : {provider.upper()}" + (" (via Portkey)" if use_portkey else ""))
        print(f"Model    : {model_name}")
        print(f"Folder   : {input_folder_name}")
        print(f"Examples : {len(examples)} calibration example(s) loaded")
        if style_analysis:
            print(f"Guide    : style guide loaded")
        if CALIBRATION_TEST_SKIP_CALIBRATION:
            print(f"Images   : {actual_count} image(s) (skipping first {skip} used for calibration)")
        else:
            print(f"Images   : first {actual_count} image(s)")
        if collection_context:
            print(f"Context  : collection-context.txt loaded")
        print()

        timestamp = datetime.now().strftime("%Y-%m-%d_Time_%H-%M-%S")
        folder_slug = input_folder_name.replace(os.sep, "-").replace("/", "-")
        output_folder_name = f"AltText_{folder_slug}_calibration_test_{model_name}_{timestamp}"
        output_dir = os.path.join(script_dir, "output_folders", output_folder_name)
        os.makedirs(os.path.join(output_dir, "metadata", "json"), exist_ok=True)

        script_start = time.time()
        results, issues, total_in_tokens, total_out_tokens = process_image_list(
            test_images, prompt, provider, client, model_name, images_per_call, actual_count, 0,
            relationship=RELATIONSHIP_BETWEEN_IMAGES_PER_CALL
        )
        total_time = time.time() - script_start

        summary = {
            "provider": provider,
            "model": model_name,
            "use_portkey": use_portkey,
            "image_folder": input_folder_name,
            "calibration_test_run": True,
            "calibration_examples_used": len(examples),
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
        if style_analysis:
            summary["style_analysis"] = style_analysis

        output = {"summary": summary, "results": results}
        json_path = os.path.join(output_dir, "metadata", "json", "alt_text_results.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nCALIBRATION TEST COMPLETE")
        print(f"Processed : {actual_count - len(issues)}/{actual_count} images")
        if issues:
            print(f"Failed    : {len(issues)}")
        print(f"Tokens    : {total_in_tokens + total_out_tokens:,}  (in: {total_in_tokens:,}, out: {total_out_tokens:,})")
        print(f"Time      : {total_time:.1f}s")
        print(f"Output    : output_folders/{output_folder_name}/")

        if RUN_HTML_REVIEW:
            print(f"\n{'='*60}")
            print(f"STEP 2 — HTML Review")
            print(f"{'='*60}")
            subprocess.run(
                [sys.executable, os.path.join(script_dir, "step-2-html-review.py"),
                 "--folder", output_dir],
                cwd=script_dir,
            )

        print(f"\n{'='*60}")
        print(f"NEXT STEPS")
        print(f"{'='*60}")
        if RUN_HTML_REVIEW:
            print(f"  1. Open the review interface in your browser:")
            print(f"       output_folders/{output_folder_name}/review/review_index.html")
            print(f"     Check whether the style guide is being applied correctly.")
        else:
            print(f"  1. Create the HTML review interface:")
            print(f"       python step-2-html-review.py --folder output_folders/{output_folder_name}")
            print(f"     Check whether the style guide is being applied correctly.")
        print(f"\n  2. If the outputs need refinement, edit the examples file directly:")
        print(f"       {input_folder_name}/collection-examples.txt")
        print(f"     Adjust the examples or the style guide, then re-run the test:")
        print(f"       python step-0-calibration.py --test")
        print(f"\n  3. When satisfied, run the full image analysis:")
        print(f"       python run.py")
        print(f"{'='*60}")

        return 0 if not issues else 1

    # -------------------------------------------------------------------------
    # CALIBRATION MODE — create baseline examples (no prior examples)
    # -------------------------------------------------------------------------
    count = CALIBRATION_COUNT
    sample_images = all_images[:count]
    actual_count = len(sample_images)

    print(f"\nCALIBRATION — Step 0: Sample Image Analysis")
    print(f"Provider : {provider.upper()}" + (" (via Portkey)" if use_portkey else ""))
    print(f"Model    : {model_name}")
    print(f"Folder   : {input_folder_name}")
    print(f"Sample   : first {actual_count} images")
    if collection_context:
        print(f"Context  : collection-context.txt loaded")
    print(f"\nFound {total_in_folder} image(s) total — processing first {actual_count}\n")

    prompt = STEP1_PROMPT.format(collection_context=collection_context, collection_examples="")

    timestamp = datetime.now().strftime("%Y-%m-%d_Time_%H-%M-%S")
    folder_slug = input_folder_name.replace(os.sep, "-").replace("/", "-")
    output_folder_name = f"AltText_{folder_slug}_calibration_{model_name}_{timestamp}"
    output_dir = os.path.join(script_dir, "output_folders", output_folder_name)
    os.makedirs(os.path.join(output_dir, "metadata", "json"), exist_ok=True)

    script_start = time.time()
    results, issues, total_in_tokens, total_out_tokens = process_image_list(
        sample_images, prompt, provider, client, model_name, images_per_call, actual_count, 0,
        relationship=RELATIONSHIP_BETWEEN_IMAGES_PER_CALL
    )
    total_time = time.time() - script_start

    summary = {
        "provider": provider,
        "model": model_name,
        "use_portkey": use_portkey,
        "image_folder": input_folder_name,
        "calibration_run": True,
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

    print(f"\nCALIBRATION COMPLETE")
    print(f"Processed : {actual_count - len(issues)}/{actual_count} images")
    if issues:
        print(f"Failed    : {len(issues)}")
    print(f"Tokens    : {total_in_tokens + total_out_tokens:,}  (in: {total_in_tokens:,}, out: {total_out_tokens:,})")
    print(f"Time      : {total_time:.1f}s")
    print(f"Output    : output_folders/{output_folder_name}/")

    if RUN_HTML_REVIEW:
        print(f"\n{'='*60}")
        print(f"STEP 2 — HTML Review")
        print(f"{'='*60}")
        subprocess.run(
            [sys.executable, os.path.join(script_dir, "step-2-html-review.py"),
             "--folder", output_dir],
            cwd=script_dir,
        )

    print(f"\n{'='*60}")
    print(f"NEXT STEPS")
    print(f"{'='*60}")
    if RUN_HTML_REVIEW:
        print(f"  1. Open the review interface in your browser:")
        print(f"       output_folders/{output_folder_name}/review/review_index.html")
        print(f"     Edit alt text as needed, then click 'Export Decisions' to download the decisions JSON.")
    else:
        print(f"  1. Create the HTML review interface:")
        print(f"       python step-2-html-review.py --folder output_folders/{output_folder_name}")
        print(f"     Review each image, edit the alt text as needed,")
        print(f"     then click 'Export Decisions' to download the decisions JSON.")
    print(f"\n  2. Move the exported JSON into:")
    print(f"       output_folders/{output_folder_name}/review/exports/")
    print(f"\n  3. Create the calibration examples and style guide text file:")
    print(f"       python integrate_edits.py --folder output_folders/{output_folder_name} --export")
    print(f"     This writes collection-examples.txt to: {input_folder_name}/")
    print(f"\n  4. To verify the style guide on fresh images, run:")
    print(f"       python step-0-calibration.py --test")
    print(f"\n  5. Edit the style guide and calibration examples, re-running the test mode to verify until satisfied with the result.")
    print(f"\n  6. To run the full image analysis:")
    print(f"       python run.py")
    print(f"\n  7. To edit the outputs of the full run:")
    print(f"\n     open interface, make edits, export decisions, save exported json to exports subfolder, and")
    print(f"       run python integrate_edits.py")
    print(f"{'='*60}")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
