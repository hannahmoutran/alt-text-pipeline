#!/usr/bin/env python3
"""
Alt Text Pipeline — Runner

Usage:
    python run.py           # Run the pipeline
    python run.py --config  # Show current configuration
"""

import os
import sys
import subprocess
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config import get_step1_config, get_image_folders, print_current_config, RUN_HTML_REVIEW


def find_newest_output_folder():
    """Return path to the most recently modified AltText_ output folder."""
    base_dir = os.path.join(script_dir, "output_folders")
    if not os.path.exists(base_dir):
        return None
    folders = [
        os.path.join(base_dir, d)
        for d in os.listdir(base_dir)
        if d.startswith("AltText_") and os.path.isdir(os.path.join(base_dir, d))
    ]
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def run_html_review(folder_path=None):
    """Run html_review.py for the given output folder (or newest if not specified)."""
    if folder_path is None:
        folder_path = find_newest_output_folder()
        if not folder_path:
            print("No AltText_ output folders found.")
            return False

    script_path = os.path.join(script_dir, "step-2-html-review.py")
    if not os.path.exists(script_path):
        print(f"Error: step-2-html-review.py not found at {script_path}")
        return False

    print(f"\n{'='*55}")
    print(f"STEP 2 — HTML Review")
    print(f"{'='*55}")
    result = subprocess.run(
        [sys.executable, script_path, "--folder", folder_path],
        cwd=script_dir,
    )
    return result.returncode == 0


def run_step1(image_folder=None):
    """Run step-1-image-analysis.py for a given image folder."""
    config = get_step1_config(image_folder)

    env = os.environ.copy()
    env['CONFIG_PROVIDER'] = config['provider']
    env['CONFIG_MODEL'] = config['model']
    env['CONFIG_IMAGE_FOLDER'] = config['image_folder']
    env['CONFIG_USE_PORTKEY'] = 'true' if config.get('use_portkey') else 'false'
    env['CONFIG_IMAGES_PER_CALL'] = str(config.get('images_per_call', 1))

    script_path = os.path.join(script_dir, "step-1-image-analysis.py")
    if not os.path.exists(script_path):
        print(f"Error: step-1-image-analysis.py not found at {script_path}")
        return False

    print(f"\n{'='*55}")
    print(f"STEP 1 — Image Analysis")
    print(f"{'='*55}")
    result = subprocess.run([sys.executable, script_path], env=env, cwd=script_dir)
    return result.returncode == 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--config', '-c'):
        print_current_config()
        return 0

    print_current_config()

    folders = get_image_folders()
    if len(folders) > 1:
        print(f"Will process {len(folders)} folders sequentially: {', '.join(folders)}\n")

    run_review = RUN_HTML_REVIEW

    start_time = datetime.now()
    results = {}

    for folder in folders:
        if len(folders) > 1:
            print(f"\n{'#'*55}")
            print(f"FOLDER: {folder}")
            print(f"{'#'*55}")
        success = run_step1(folder)
        results[folder] = success
        if success and run_review:
            run_html_review()

    duration = datetime.now() - start_time

    print(f"\n{'='*55}")
    print("SUMMARY")
    print(f"{'='*55}")
    print(f"Duration: {duration}")
    for folder, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {folder}: {status}")
    print("=" * 55)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
