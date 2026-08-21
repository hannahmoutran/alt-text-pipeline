#!/usr/bin/env python3
"""
Alt Text — Integrate Reviewer Edits
=====================================

Reads reviewer decisions exported from html_review.py and applies them back
into alt_text_results.json.

What this script does:
1. Finds the latest decisions export in review/exports/ (or use --decisions)
2. Loads alt_text_results.json from the output folder
3. Applies alt text edits from reviewer decisions
4. Saves updated alt_text_results.json (edited records gain original_alt_text)
5. Generates metadata/json/edit_report.json  (change statistics)

Usage:
    python integrate_edits.py
    python integrate_edits.py --folder output_folders/AltText_...
    python integrate_edits.py --decisions path/to/decisions.json
    python integrate_edits.py --yes
"""

import os
import sys
import json
import argparse
from datetime import datetime
from difflib import SequenceMatcher

script_dir = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Folder / export discovery
# ---------------------------------------------------------------------------

def find_newest_output_folder(base_dir):
    """Return the path to the most recently modified AltText_ folder."""
    if not os.path.exists(base_dir):
        return None
    folders = [
        os.path.join(base_dir, d)
        for d in os.listdir(base_dir)
        if d.startswith("AltText_") and os.path.isdir(os.path.join(base_dir, d))
    ]
    return max(folders, key=os.path.getmtime) if folders else None


def list_output_folders(base_dir):
    if not os.path.exists(base_dir):
        return []
    folders = [
        (d, os.path.join(base_dir, d))
        for d in os.listdir(base_dir)
        if d.startswith("AltText_") and os.path.isdir(os.path.join(base_dir, d))
    ]
    folders.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)
    return folders


def prompt_for_folder(base_dir):
    folders = list_output_folders(base_dir)
    if not folders:
        print("No AltText_ output folders found in: " + base_dir)
        return None
    print("\nAvailable output folders:")
    print("-" * 70)
    for idx, (name, path) in enumerate(folders, 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        marker = "  (newest)" if idx == 1 else ""
        print("  " + str(idx) + ". " + name + marker)
        print("       Modified: " + mtime)
    print("-" * 70)
    print("Enter a number to select, or press Enter for the newest folder.")
    while True:
        choice = input("\nSelect folder: ").strip()
        if choice == "":
            return folders[0][1]
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                return folders[idx][1]
            print("Invalid choice. Enter 1-" + str(len(folders)) + ".")
            continue
        if os.path.isdir(choice):
            return choice
        print("Invalid input.")


def find_latest_export(exports_folder):
    """Return the path to the most recent decisions JSON in exports/."""
    if not os.path.exists(exports_folder):
        return None
    json_files = [f for f in os.listdir(exports_folder) if f.endswith('.json')]
    if not json_files:
        return None
    json_files.sort(
        key=lambda f: os.path.getmtime(os.path.join(exports_folder, f)),
        reverse=True
    )
    return os.path.join(exports_folder, json_files[0])


def list_exports(exports_folder):
    if not os.path.exists(exports_folder):
        return []
    files = [
        (f, os.path.join(exports_folder, f))
        for f in os.listdir(exports_folder)
        if f.endswith('.json')
    ]
    files.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)
    return files


def prompt_for_decisions(exports_folder):
    exports = list_exports(exports_folder)
    if not exports:
        print("\nNo JSON export files found in: " + exports_folder)
        print("Export decisions from the HTML review interface and place the file there.")
        while True:
            path = input("\nPath to decisions JSON (or 'q' to quit): ").strip()
            if path.lower() == 'q':
                return None
            if os.path.isfile(path) and path.endswith('.json'):
                return path
            print("Invalid path.")

    print("\nAvailable decisions exports:")
    print("-" * 70)
    for idx, (name, path) in enumerate(exports, 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        marker = "  (newest)" if idx == 1 else ""
        print("  " + str(idx) + ". " + name + marker)
        print("       Modified: " + mtime)
    print("-" * 70)
    print("Enter a number to select, or press Enter for the newest export.")
    while True:
        choice = input("\nSelect export: ").strip()
        if choice == "":
            return exports[0][1]
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(exports):
                return exports[idx][1]
            print("Invalid choice. Enter 1-" + str(len(exports)) + ".")
            continue
        if os.path.isfile(choice) and choice.endswith('.json'):
            return choice
        print("Invalid input.")


# ---------------------------------------------------------------------------
# Integrator
# ---------------------------------------------------------------------------

class AltTextEditsIntegrator:
    """Applies reviewer decisions back into alt_text_results.json."""

    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.json_dir = os.path.join(folder_path, "metadata", "json")
        self.review_folder = os.path.join(folder_path, "review")
        self.exports_folder = os.path.join(self.review_folder, "exports")

        self.decisions_data = None
        self.original_data = None
        self.results = []
        self.summary = {}
        self.changelog = []

        self.stats = {
            'reviewer_name': '',
            'export_timestamp': '',
            'integration_timestamp': '',
            'total_records': 0,
            'total_decisions': 0,
            'approved_unchanged': 0,
            'edited': 0,
            'total_chars_changed': 0,
        }

    # -----------------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------------

    def load_decisions(self, decisions_path):
        try:
            with open(decisions_path, 'r', encoding='utf-8') as f:
                self.decisions_data = json.load(f)
            self.stats['reviewer_name'] = self.decisions_data.get('reviewer_name', 'Unknown')
            self.stats['export_timestamp'] = self.decisions_data.get('export_timestamp', '')
            self.stats['total_decisions'] = len(self.decisions_data.get('decisions', []))
            print("Loaded " + str(self.stats['total_decisions']) + " decisions")
            print("Reviewer: " + self.stats['reviewer_name'])
            return True
        except Exception as exc:
            print("Error loading decisions: " + str(exc))
            return False

    def load_results_json(self):
        json_path = os.path.join(self.json_dir, "alt_text_results.json")
        if not os.path.exists(json_path):
            print("Error: alt_text_results.json not found at: " + json_path)
            return False
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.original_data = json.load(f)
            self.summary = self.original_data.get('summary', {})
            self.results = self.original_data.get('results', [])
            self.stats['total_records'] = len(self.results)
            print("Loaded " + str(len(self.results)) + " image records")
            return True
        except Exception as exc:
            print("Error loading alt_text_results.json: " + str(exc))
            return False

    # -----------------------------------------------------------------------
    # Diff helper
    # -----------------------------------------------------------------------

    def _char_diff(self, original, new_value):
        original = str(original) if original else ""
        new_value = str(new_value) if new_value else ""
        matcher = SequenceMatcher(None, original, new_value)
        added, deleted, unchanged = 0, 0, 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                unchanged += i2 - i1
            elif tag == 'delete':
                deleted += i2 - i1
            elif tag == 'insert':
                added += j2 - j1
            elif tag == 'replace':
                deleted += i2 - i1
                added += j2 - j1
        return {'chars_added': added, 'chars_deleted': deleted, 'chars_unchanged': unchanged}

    # -----------------------------------------------------------------------
    # Apply edits
    # -----------------------------------------------------------------------

    def apply_edits(self):
        if not self.decisions_data:
            return False

        decisions_by_id = {
            d['record_id']: d
            for d in self.decisions_data.get('decisions', [])
        }

        for idx, rec in enumerate(self.results):
            record_id = idx + 1
            decision = decisions_by_id.get(record_id)
            if not decision:
                continue

            original_alt = rec.get('alt_text', '')
            final_alt = decision.get('final_alt_text', original_alt)
            approved = decision.get('approved', False)
            edited = decision.get('edited', False)
            notes = decision.get('reviewer_notes', '')

            rec['reviewer_approved'] = approved
            rec['reviewer_name'] = self.stats['reviewer_name']
            rec['reviewer_date'] = self.stats['export_timestamp']
            if notes:
                rec['reviewer_notes'] = notes

            if edited and final_alt != original_alt:
                diff = self._char_diff(original_alt, final_alt)
                rec['alt_text'] = final_alt
                rec['original_alt_text'] = original_alt
                self.stats['edited'] += 1
                self.stats['total_chars_changed'] += diff['chars_added'] + diff['chars_deleted']

                self.changelog.append({
                    'record_id': record_id,
                    'filename': rec.get('filename', ''),
                    'original': original_alt,
                    'final': final_alt,
                    'diff': diff,
                    'approved': approved,
                    'reviewer_notes': notes,
                })
            elif approved:
                self.stats['approved_unchanged'] += 1

        return True

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------

    def save_updated_json(self):
        out_data = {'summary': self.summary, 'results': self.results}
        out_path = os.path.join(self.json_dir, "alt_text_results.json")
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(out_data, f, indent=2, ensure_ascii=False)
            print("  Saved updated alt_text_results.json")
            return True
        except Exception as exc:
            print("  Error saving: " + str(exc))
            return False

    def generate_edit_report(self):
        """Write a JSON report of edit statistics and change log."""
        self.stats['integration_timestamp'] = datetime.now().isoformat()

        report = {
            'batch_info': {
                'reviewer': self.stats['reviewer_name'],
                'export_timestamp': self.stats['export_timestamp'],
                'integration_timestamp': self.stats['integration_timestamp'],
                'folder': self.folder_name,
                'model': self.summary.get('model', ''),
                'provider': self.summary.get('provider', ''),
                'total_records': self.stats['total_records'],
                'total_decisions': self.stats['total_decisions'],
            },
            'summary': {
                'approved_unchanged': self.stats['approved_unchanged'],
                'edited': self.stats['edited'],
                'total_chars_changed': self.stats['total_chars_changed'],
            },
            'edits': self.changelog,
        }

        out_path = os.path.join(self.json_dir, "edit_report.json")
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("  Generated edit_report.json")
            return out_path
        except Exception as exc:
            print("  Error: " + str(exc))
            return None

    # -----------------------------------------------------------------------
    # Grounding export
    # -----------------------------------------------------------------------

    def export_grounding(self):
        """Write collection-examples.txt to the image folder for use as grounding examples."""
        image_folder = self.summary.get('image_folder', '')
        if not image_folder:
            print("  Error: image_folder not found in summary — cannot write examples file.")
            return False

        target_folder = os.path.join(script_dir, image_folder)
        if not os.path.isdir(target_folder):
            print(f"  Error: image folder not found: {target_folder}")
            return False

        examples_path = os.path.join(target_folder, "collection-examples.txt")
        lines = [
            "# Collection Examples",
            "# Reviewed and edited by an archivist.",
            "# Original: AI-generated alt text  |  Alt Text: archivist's correction",
            "# The AI will analyze these differences to match the archivist's style.",
            "",
        ]
        exported = 0
        for rec in self.results:
            alt_text = rec.get('alt_text', '')
            if not alt_text:
                continue
            original = rec.get('original_alt_text', alt_text)
            lines.append(f"Image: {rec['filename']}")
            lines.append(f"Original: {original}")
            lines.append(f"Alt Text: {alt_text}")
            lines.append("")
            exported += 1

        with open(examples_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"  Wrote {exported} grounding examples to: {examples_path}")

        # Generate a style guide from the corrected examples so the archivist
        # can review and edit it before running step 1.
        try:
            sys.path.insert(0, script_dir)
            from pipeline_core import read_examples_file, generate_style_analysis, init_client
            provider = self.summary.get('provider', '')
            model = self.summary.get('model', '')
            use_portkey = self.summary.get('use_portkey', False)
            if provider and model:
                client = init_client(provider, use_portkey)
                examples = read_examples_file(target_folder)
                style_analysis = generate_style_analysis(examples, provider, client, model)
                if style_analysis:
                    with open(examples_path, 'a', encoding='utf-8') as f:
                        f.write(f"\n# Style Guide\n{style_analysis}\n")
                    print(f"\n{style_analysis}")
                    print(f"\n  Style guide appended to collection-examples.txt")
        except Exception as e:
            print(f"  Warning: could not generate style guide: {e}")

        return True

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    def print_summary(self):
        print("\n" + "=" * 60)
        print("INTEGRATION SUMMARY")
        print("=" * 60)
        print("Reviewer      : " + self.stats['reviewer_name'])
        print("Total records : " + str(self.stats['total_records']))
        print("Decisions     : " + str(self.stats['total_decisions']))
        print("Approved (no edit): " + str(self.stats['approved_unchanged']))
        print("Edited        : " + str(self.stats['edited']))
        if self.stats['edited'] > 0:
            print("Chars changed : " + str(self.stats['total_chars_changed']))
            print("\nEdited records:")
            for entry in self.changelog:
                print("  [" + str(entry['record_id']) + "] " + entry['filename'])
                diff = entry.get('diff', {})
                print("    +" + str(diff.get('chars_added', 0))
                      + " / -" + str(diff.get('chars_deleted', 0)) + " chars")

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    def run(self, decisions_path=None, export_grounding=False):
        print("\n" + "=" * 60)
        print("Alt Text — Integrate Reviewer Edits")
        print("=" * 60)
        print("Folder: " + self.folder_name)

        print("\n1. Locating decisions export...")
        if decisions_path:
            if not os.path.exists(decisions_path):
                print("Error: not found: " + decisions_path)
                return False
            print("  Using: " + os.path.basename(decisions_path))
        else:
            decisions_path = find_latest_export(self.exports_folder)
            if not decisions_path:
                print("Error: no JSON files found in " + self.exports_folder)
                print("Export decisions from the HTML review interface first.")
                return False
            print("  Found: " + os.path.basename(decisions_path))

        print("\n2. Loading decisions...")
        if not self.load_decisions(decisions_path):
            return False

        print("\n3. Loading alt text results...")
        if not self.load_results_json():
            return False

        print("\n4. Applying edits...")
        if not self.apply_edits():
            return False
        print("  Applied edits: " + str(self.stats['edited']) + " records modified")

        print("\n5. Saving updated JSON...")
        if not self.save_updated_json():
            return False

        print("\n6. Generating edit report...")
        self.generate_edit_report()

        if export_grounding:
            print("\n7. Exporting grounding examples...")
            self.export_grounding()

        self.print_summary()

        print("\n" + "=" * 60)
        print("INTEGRATION COMPLETE")
        print("=" * 60)
        print("Output folder: " + self.json_dir)
        print("  alt_text_results.json  (updated in place)")
        print("  edit_report.json       (change statistics)")
        print("=" * 60)
        return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Apply reviewer edits from html_review.py back into alt_text_results.json.'
    )
    parser.add_argument('--folder', '-f', help='Path to AltText_ output folder.')
    parser.add_argument('--decisions', '-d', help='Path to specific decisions JSON file.')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt.')
    parser.add_argument('--export-grounding', '-g', action='store_true',
        help='After integrating, write collection-examples.txt to the image folder for use in the full run.')
    args = parser.parse_args()

    base_output_dir = os.path.join(script_dir, "output_folders")

    print("Alt Text — Integrate Reviewer Edits")
    print("=" * 60)

    if args.folder:
        folder_path = args.folder
        if not os.path.isdir(folder_path):
            print("Error: folder not found: " + folder_path)
            return 1
        print("Using folder: " + os.path.basename(folder_path))
    else:
        folder_path = prompt_for_folder(base_output_dir)
        if not folder_path:
            return 1
        print("Selected: " + os.path.basename(folder_path))

    if args.decisions:
        decisions_path = args.decisions
        if not os.path.exists(decisions_path):
            print("Error: decisions file not found: " + decisions_path)
            return 1
        print("Using decisions: " + os.path.basename(decisions_path))
    else:
        exports_folder = os.path.join(folder_path, "review", "exports")
        decisions_path = prompt_for_decisions(exports_folder)
        if not decisions_path:
            print("Operation cancelled.")
            return 0
        print("Selected: " + os.path.basename(decisions_path))

    if not args.yes:
        print("\n" + "-" * 60)
        print("Summary:")
        print("  Output folder : " + os.path.basename(folder_path))
        print("  Decisions file: " + os.path.basename(decisions_path))
        print("-" * 60)
        response = input(
            "\nThis will modify alt_text_results.json in place. Continue? (yes/no): "
        ).strip().lower()
        if response not in ('yes', 'y'):
            print("Operation cancelled.")
            return 0

    integrator = AltTextEditsIntegrator(folder_path)
    success = integrator.run(decisions_path=decisions_path, export_grounding=args.export_grounding)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
