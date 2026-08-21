#!/usr/bin/env python3
"""
Alt Text HTML Review Interface
================================

Generates a local HTML review interface for alt text pipeline output.
Shows each image large with the generated alt text in a box below;
allows editing or approving.

After running step-1-image-analysis.py, run this to review results:

Usage:
    python html_review.py
    python html_review.py --folder output_folders/AltText_...
    python html_review.py --records-per-page 10

Then open the generated HTML file in your browser.
Export your decisions and pass them to integrate_edits.py.
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Folder discovery
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
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def list_output_folders(base_dir):
    """Return (name, path) tuples for AltText_ folders, newest first."""
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
    """Interactively prompt the user to select an output folder."""
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
        print("Invalid input. Enter a number or a folder path.")


# ---------------------------------------------------------------------------
# Main builder class
# ---------------------------------------------------------------------------

class AltTextHTMLReviewBuilder:
    """Builds an interactive HTML review page for alt text pipeline output."""

    def __init__(self, folder_path, records_per_page=10):
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.records_per_page = records_per_page
        self.results = []
        self.summary = {}
        self.review_folder = ""
        self.images_folder = ""

        # A stable timestamp slug for localStorage namespacing
        parts = self.folder_name.split('_')
        if len(parts) >= 2:
            self.session_key = '_'.join(parts[-2:])
        else:
            self.session_key = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # -----------------------------------------------------------------------
    # Data loading
    # -----------------------------------------------------------------------

    def load_json(self):
        """Load alt_text_results.json from the output folder."""
        json_path = os.path.join(
            self.folder_path, "metadata", "json", "alt_text_results.json"
        )
        if not os.path.exists(json_path):
            print("Error: alt_text_results.json not found at: " + json_path)
            return False

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as exc:
            print("Error loading JSON: " + str(exc))
            return False

        self.summary = data.get('summary', {})
        self.results = data.get('results', [])
        print("Loaded " + str(len(self.results)) + " image records")
        return True

    # -----------------------------------------------------------------------
    # File setup
    # -----------------------------------------------------------------------

    def create_review_folder(self):
        """Create review/, review/images/, and review/exports/ directories."""
        self.review_folder = os.path.join(self.folder_path, "review")
        self.images_folder = os.path.join(self.review_folder, "images")
        exports_folder = os.path.join(self.review_folder, "exports")

        os.makedirs(self.review_folder, exist_ok=True)
        os.makedirs(self.images_folder, exist_ok=True)
        os.makedirs(exports_folder, exist_ok=True)
        print("Created review folder: " + self.review_folder)
        return True

    def copy_images(self):
        """Copy original images into review/images/ for portability."""
        copied = 0
        skipped = 0
        for rec in self.results:
            image_path = rec.get('image_path', '')
            if not image_path:
                continue
            if os.path.exists(image_path):
                dest = os.path.join(self.images_folder, os.path.basename(image_path))
                try:
                    shutil.copy2(image_path, dest)
                    copied += 1
                except Exception as exc:
                    print("Warning: could not copy " + os.path.basename(image_path) + ": " + str(exc))
            else:
                skipped += 1
        print("Copied " + str(copied) + " images" + (" (skipped " + str(skipped) + " not found)" if skipped else ""))
        return True

    # -----------------------------------------------------------------------
    # HTML helpers
    # -----------------------------------------------------------------------

    def esc(self, text):
        """Escape HTML special characters."""
        if text is None:
            return ""
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))

    def esc_js(self, text):
        """Escape text for embedding inside a JavaScript string literal."""
        if text is None:
            return ""
        return (str(text)
                .replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r"))

    # -----------------------------------------------------------------------
    # CSS
    # -----------------------------------------------------------------------

    def get_css(self):
        return """
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            font-size: 15px;
            margin: 0;
            padding: 20px;
            background-color: #f0f2f5;
            line-height: 1.5;
            color: #222;
        }

        .header {
            background: #2c3e50;
            color: white;
            padding: 22px 24px;
            border-radius: 4px;
            margin-bottom: 22px;
        }
        .header h1 { margin: 0 0 6px 0; font-size: 22px; }
        .header p { margin: 3px 0; opacity: 0.85; font-size: 14px; }

        .progress-bar-wrap {
            background: white;
            padding: 14px 18px;
            border-radius: 4px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .progress-label { font-size: 13px; color: #555; margin-bottom: 6px; }
        .progress-bar {
            width: 100%; height: 14px;
            background: #dde2e8; border-radius: 8px; overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #2980b9, #3498db);
            transition: width 0.3s;
        }

        .navigation {
            background: white;
            padding: 12px 18px;
            border-radius: 4px;
            margin-bottom: 22px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .nav-btn {
            background: #2980b9;
            color: white;
            padding: 7px 16px;
            text-decoration: none;
            border-radius: 4px;
            margin: 0 6px;
            font-weight: bold;
            display: inline-block;
            border: none;
            cursor: pointer;
            font-size: 13px;
        }
        .nav-btn:hover { background: #1a6fa3; }
        .nav-btn.disabled { background: #aab; pointer-events: none; }

        .export-bar {
            background: white;
            padding: 14px 18px;
            border-radius: 4px;
            margin-bottom: 22px;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .export-btn {
            background: #2c3e50;
            color: white;
            border: none;
            padding: 9px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            font-size: 13px;
            letter-spacing: 0.03em;
        }
        .export-btn:hover { background: #1a252f; }
        .export-note { font-size: 13px; color: #666; }

        /* --- Image record card --- */
        .record {
            background: white;
            border: 1px solid #dce1e8;
            border-radius: 6px;
            margin-bottom: 32px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.06);
            overflow: hidden;
        }
        .record.approved { border-left: 5px solid #27ae60; }
        .record.has-edits { border-left: 5px solid #e67e22; }

        .record-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 20px;
            border-bottom: 1px solid #eaecef;
            background: #f7f8fa;
        }
        .record-title {
            font-size: 16px;
            font-weight: 700;
            color: #2c3e50;
        }
        .record-meta { font-size: 12px; color: #888; margin-top: 2px; }

        .reviewed-label {
            display: flex;
            align-items: center;
            gap: 7px;
            font-size: 14px;
            color: #444;
            cursor: pointer;
            white-space: nowrap;
        }
        .reviewed-label input { width: 17px; height: 17px; cursor: pointer; }

        /* Large image */
        .image-wrap {
            padding: 20px 20px 12px 20px;
            text-align: center;
            background: #f0f2f5;
        }
        .image-container {
            position: relative;
            display: inline-block;
            max-width: 100%;
        }
        .image-container img {
            max-width: 800px;
            width: 100%;
            height: auto;
            border: 2px solid #cfd5dc;
            border-radius: 4px;
            display: block;
            transform-origin: 0 0;
            cursor: grab;
            user-select: none;
            -webkit-user-drag: none;
        }
        .image-container img.panning { cursor: grabbing; }
        .zoom-controls {
            position: absolute;
            top: 8px;
            right: 8px;
            display: flex;
            gap: 4px;
            z-index: 10;
        }
        .zoom-btn {
            background: rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.25);
            color: #fff;
            font-size: 15px;
            font-weight: bold;
            width: 28px;
            height: 28px;
            border-radius: 4px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .zoom-btn:hover { background: rgba(0,0,0,0.75); }
        .zoom-hint { font-size: 11px; color: #aaa; margin-top: 6px; }
        .image-filename { font-size: 12px; color: #888; margin-top: 4px; word-break: break-all; }

        /* Alt text area */
        .alt-text-section {
            padding: 18px 20px 4px 20px;
        }
        .field-label {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            color: #555;
            margin-bottom: 7px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .edit-badge {
            font-size: 11px;
            background: #e67e22;
            color: white;
            padding: 1px 7px;
            border-radius: 10px;
            font-weight: normal;
            text-transform: none;
            letter-spacing: 0;
        }
        .alt-text-input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #cfd5dc;
            border-radius: 4px;
            font-size: 14px;
            font-family: inherit;
            line-height: 1.6;
            resize: none;
            overflow: hidden;
            background: #fcfdfe;
        }
        .alt-text-input:focus {
            border-color: #2980b9;
            outline: none;
            box-shadow: 0 0 0 2px rgba(41,128,185,0.18);
        }
        .alt-text-input.edited {
            border-color: #e67e22;
            background: #fff8f2;
        }

        /* Action buttons */
        .record-actions {
            padding: 12px 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .approve-btn {
            background: #27ae60;
            color: white;
            border: none;
            padding: 8px 18px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
        }
        .approve-btn:hover { background: #1e8449; }
        .restore-btn {
            background: #95a5a6;
            color: white;
            border: none;
            padding: 8px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .restore-btn:hover { background: #7f8c8d; }
        .restore-btn[style*="none"] { display: none; }

        /* Notes */
        .notes-section {
            padding: 4px 20px 18px 20px;
        }
        .notes-input {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid #dce1e8;
            border-radius: 4px;
            font-size: 13px;
            font-family: inherit;
            color: #555;
            resize: vertical;
            min-height: 44px;
            background: #fafbfc;
        }
        .notes-input:focus {
            border-color: #2980b9;
            outline: none;
        }
        .notes-input::placeholder { color: #bbb; }

        /* Summary grid */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }
        .summary-card {
            background: white;
            padding: 14px;
            border-radius: 4px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .summary-card .number { font-size: 28px; font-weight: 700; color: #2c3e50; }
        .summary-card .label { color: #888; font-size: 13px; }

        /* Page links (index) */
        .page-links {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        .page-link {
            background: #2980b9;
            color: white;
            padding: 12px;
            text-decoration: none;
            border-radius: 4px;
            text-align: center;
            font-weight: 600;
            font-size: 14px;
        }
        .page-link:hover { background: #1a6fa3; }
        """

    # -----------------------------------------------------------------------
    # JavaScript
    # -----------------------------------------------------------------------

    def get_javascript(self):
        return f"""
        const STORAGE_PREFIX = 'alttext-review-{self.esc_js(self.session_key)}-';
        const FOLDER_NAME = '{self.esc_js(self.folder_name)}';

        function autoResize(el) {{
            el.style.height = 'auto';
            el.style.height = el.scrollHeight + 'px';
        }}

        function setStorage(key, value) {{
            try {{ localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value)); }}
            catch(e) {{ console.error('Storage write error:', e); }}
        }}

        function getStorage(key, def) {{
            if (def === undefined) def = null;
            try {{
                const raw = localStorage.getItem(STORAGE_PREFIX + key);
                return raw !== null ? JSON.parse(raw) : def;
            }} catch(e) {{ return def; }}
        }}

        function promptForReviewerName() {{
            let name = getStorage('reviewer-name', null);
            if (!name) {{
                name = prompt('Welcome! Enter your name for this review session:');
                if (name && name.trim()) setStorage('reviewer-name', name.trim());
            }}
            return name;
        }}

        function updateProgress() {{
            const total = parseInt(document.body.dataset.totalRecords || '0');
            let done = 0;
            for (let i = 1; i <= total; i++) {{
                if (getStorage('approved-' + i, false)) done++;
            }}
            const fill = document.getElementById('progress-fill');
            const text = document.getElementById('progress-text');
            if (fill) fill.style.width = (total > 0 ? done / total * 100 : 0) + '%';
            if (text) text.textContent = done + ' / ' + total + ' approved';
        }}

        function updateRecordStyle(id) {{
            const el = document.getElementById('record-' + id);
            if (!el) return;
            const approved = getStorage('approved-' + id, false);
            const edited = getStorage('edited-' + id, false);
            el.classList.toggle('approved', approved);
            el.classList.toggle('has-edits', edited && !approved);
        }}

        function storeOriginal(id) {{
            const key = 'original-' + id;
            if (getStorage(key, null) === null) {{
                const ta = document.getElementById('alttext-' + id);
                if (ta) setStorage(key, ta.value);
            }}
        }}

        function onAltTextChange(id) {{
            storeOriginal(id);
            const ta = document.getElementById('alttext-' + id);
            const original = getStorage('original-' + id, '');
            const current = ta ? ta.value : '';
            const isEdited = current !== original;
            setStorage('edited-' + id, isEdited);
            setStorage('current-' + id, current);

            if (ta) ta.classList.toggle('edited', isEdited);
            const badge = document.getElementById('edit-badge-' + id);
            if (badge) badge.style.display = isEdited ? 'inline' : 'none';

            // Auto-unapprove if text changes
            if (isEdited) {{
                setStorage('approved-' + id, false);
                const cb = document.getElementById('approved-cb-' + id);
                if (cb) cb.checked = false;
            }}
            updateRecordStyle(id);
            updateProgress();
        }}

        function approveRecord(id) {{
            setStorage('approved-' + id, true);
            const cb = document.getElementById('approved-cb-' + id);
            if (cb) cb.checked = true;
            updateRecordStyle(id);
            updateProgress();
        }}

        function setApproved(id, checked) {{
            setStorage('approved-' + id, checked);
            updateRecordStyle(id);
            updateProgress();
        }}

        function restoreOriginal(id) {{
            const original = getStorage('original-' + id, null);
            if (original === null) return;
            const ta = document.getElementById('alttext-' + id);
            if (ta) {{
                ta.value = original;
                autoResize(ta);
            }}
            setStorage('edited-' + id, false);
            setStorage('current-' + id, original);
            if (ta) ta.classList.remove('edited');
            const badge = document.getElementById('edit-badge-' + id);
            if (badge) badge.style.display = 'none';
            updateRecordStyle(id);
        }}

        function saveNotes(id, value) {{
            setStorage('notes-' + id, value);
        }}

        function restoreState() {{
            promptForReviewerName();
            const total = parseInt(document.body.dataset.totalRecords || '0');
            for (let i = 1; i <= total; i++) {{
                storeOriginal(i);

                // Restore edited text
                const saved = getStorage('current-' + i, null);
                const ta = document.getElementById('alttext-' + i);
                if (saved !== null && ta) {{
                    ta.value = saved;
                    autoResize(ta);
                }}
                const isEdited = getStorage('edited-' + i, false);
                if (ta) ta.classList.toggle('edited', isEdited);
                const badge = document.getElementById('edit-badge-' + i);
                if (badge) badge.style.display = isEdited ? 'inline' : 'none';

                // Restore approved checkbox
                const approved = getStorage('approved-' + i, false);
                const cb = document.getElementById('approved-cb-' + i);
                if (cb) cb.checked = approved;

                // Restore notes
                const notes = getStorage('notes-' + i, '');
                const notesEl = document.getElementById('notes-' + i);
                if (notesEl && notes) notesEl.value = notes;

                updateRecordStyle(i);
            }}
            document.querySelectorAll('textarea').forEach(autoResize);
            updateProgress();
        }}

        function exportDecisions() {{
            let reviewer = getStorage('reviewer-name', null);
            if (!reviewer) {{
                reviewer = prompt('Enter your name for the export:');
                if (reviewer && reviewer.trim()) {{
                    setStorage('reviewer-name', reviewer.trim());
                }} else {{
                    return;
                }}
            }}

            const total = parseInt(document.body.dataset.totalRecords || '0');
            const decisions = [];
            let approvedCount = 0;
            let editedCount = 0;

            for (let i = 1; i <= total; i++) {{
                const approved = getStorage('approved-' + i, false);
                const edited = getStorage('edited-' + i, false);
                const current = getStorage('current-' + i, null);
                const original = getStorage('original-' + i, null);
                const notes = getStorage('notes-' + i, '');
                const meta = getStorage('record-meta-' + i, {{}});

                if (approved || edited || notes) {{
                    if (approved) approvedCount++;
                    if (edited) editedCount++;
                    decisions.push({{
                        record_id: i,
                        filename: meta.filename || '',
                        image_path: meta.image_path || '',
                        folder: meta.folder || '',
                        approved: approved,
                        edited: edited,
                        original_alt_text: original,
                        final_alt_text: current !== null ? current : original,
                        reviewer_notes: notes
                    }});
                }}
            }}

            if (decisions.length === 0) {{
                alert('No records have been reviewed yet.');
                return;
            }}

            const exportData = {{
                export_timestamp: new Date().toISOString(),
                folder_name: FOLDER_NAME,
                reviewer_name: reviewer,
                total_records: total,
                approved_count: approvedCount,
                edited_count: editedCount,
                decisions: decisions
            }};

            const safeName = reviewer.replace(/[^\\w\\-]/g, '_');
            const dateStr = new Date().toISOString().split('T')[0];
            const filename = FOLDER_NAME + '_' + safeName + '_' + dateStr + '.json';

            const blob = new Blob([JSON.stringify(exportData, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(function() {{ URL.revokeObjectURL(url); a.remove(); }}, 100);

            alert('Exported ' + decisions.length + ' decisions to: ' + filename +
                  '\\n\\nMove this file to the review/exports/ folder, then run integrate_edits.py');
        }}

        // --- In-place image zoom and pan ---
        (function() {{
            const MIN_SCALE = 0.5, MAX_SCALE = 8, STEP = 0.25;
            const states = new WeakMap();

            function getState(c) {{
                if (!states.has(c)) states.set(c, {{ scale: 1, tx: 0, ty: 0 }});
                return states.get(c);
            }}
            function apply(c) {{
                const img = c.querySelector('img');
                if (!img) return;
                const s = getState(c);
                img.style.transform = 'translate(' + s.tx + 'px,' + s.ty + 'px) scale(' + s.scale + ')';
            }}
            window.zoomImgBtn = function(btn, delta) {{
                const c = btn.closest('.image-container');
                if (!c) return;
                const s = getState(c);
                s.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, s.scale + delta));
                apply(c);
            }};
            window.resetImgZoom = function(btn) {{
                const c = btn.closest('.image-container');
                if (!c) return;
                const s = getState(c);
                s.scale = 1; s.tx = 0; s.ty = 0;
                apply(c);
            }};

            document.addEventListener('DOMContentLoaded', function() {{
                let active = null, hovered = null;
                let dsx, dsy, dtx, dty;

                document.querySelectorAll('.image-container').forEach(function(c) {{
                    c.addEventListener('mouseenter', function() {{ hovered = c; }});
                    c.addEventListener('mouseleave', function() {{ hovered = null; }});
                    c.addEventListener('mousedown', function(e) {{
                        if (e.target.classList.contains('zoom-btn')) return;
                        if (e.button !== 0) return;
                        e.preventDefault();
                        active = c;
                        const s = getState(c);
                        dsx = e.clientX; dsy = e.clientY;
                        dtx = s.tx; dty = s.ty;
                        c.querySelector('img').classList.add('panning');
                    }});
                }});
                document.addEventListener('mousemove', function(e) {{
                    if (!active) return;
                    const s = getState(active);
                    s.tx = dtx + (e.clientX - dsx);
                    s.ty = dty + (e.clientY - dsy);
                    apply(active);
                }});
                document.addEventListener('mouseup', function() {{
                    if (active) {{
                        const img = active.querySelector('img');
                        if (img) img.classList.remove('panning');
                        active = null;
                    }}
                }});
                document.addEventListener('keydown', function(e) {{
                    if (!hovered) return;
                    const tag = document.activeElement && document.activeElement.tagName;
                    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
                    if (e.key === '+' || e.key === '=') {{
                        e.preventDefault();
                        const s = getState(hovered);
                        s.scale = Math.min(MAX_SCALE, s.scale + STEP);
                        apply(hovered);
                    }} else if (e.key === '-') {{
                        e.preventDefault();
                        const s = getState(hovered);
                        s.scale = Math.max(MIN_SCALE, s.scale - STEP);
                        apply(hovered);
                    }} else if (e.key === '0') {{
                        e.preventDefault();
                        const s = getState(hovered);
                        s.scale = 1; s.tx = 0; s.ty = 0;
                        apply(hovered);
                    }}
                }});
            }});
        }})();

        document.addEventListener('DOMContentLoaded', restoreState);
        """

    # -----------------------------------------------------------------------
    # Record HTML
    # -----------------------------------------------------------------------

    def record_html(self, rec, record_id):
        """Generate HTML for one image record."""
        filename = rec.get('filename', '')
        image_path = rec.get('image_path', '')
        folder = rec.get('folder', '')
        alt_text = rec.get('alt_text', '')
        has_error = bool(rec.get('error'))

        meta_js = (
            "<script>setStorage('record-meta-" + str(record_id) + "', {"
            "filename: '" + self.esc_js(filename) + "',"
            "image_path: '" + self.esc_js(image_path) + "',"
            "folder: '" + self.esc_js(folder) + "'"
            "});</script>"
        )

        title = str(record_id) + ". " + self.esc(filename)
        if folder and folder != filename:
            title += ' <span class="record-meta">/ ' + self.esc(folder) + '</span>'

        html = (
            '<div class="record" id="record-' + str(record_id) + '">'
            + meta_js +
            '<div class="record-header">'
            '<div><div class="record-title">' + title + '</div></div>'
            '<label class="reviewed-label">'
            '<input type="checkbox" id="approved-cb-' + str(record_id) + '"'
            ' onchange="setApproved(' + str(record_id) + ', this.checked)">'
            'Approved'
            '</label>'
            '</div>'
        )

        # Image
        html += '<div class="image-wrap">'
        if filename:
            html += (
                '<div class="image-container">'
                '<div class="zoom-controls">'
                '<button class="zoom-btn" onclick="zoomImgBtn(this, 0.25)" title="Zoom in">+</button>'
                '<button class="zoom-btn" onclick="zoomImgBtn(this, -0.25)" title="Zoom out">−</button>'
                '<button class="zoom-btn" onclick="resetImgZoom(this)" title="Reset">✕</button>'
                '</div>'
                '<img src="images/' + self.esc(filename) + '"'
                ' alt="' + self.esc(alt_text[:120]) + '"'
                ' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\';">'
                '<div style="display:none;padding:30px;color:#999;font-size:13px;">Image not available</div>'
                '</div>'
                '<div class="zoom-hint">Hover image then +/- to zoom &nbsp;|&nbsp; 0 to reset &nbsp;|&nbsp; Drag to pan</div>'
                '<div class="image-filename">' + self.esc(filename) + '</div>'
            )
        else:
            html += '<div style="padding:30px;color:#aaa;">No image</div>'
        html += '</div>'

        # Alt text field
        if has_error:
            error_msg = self.esc(rec.get('error', ''))
            html += (
                '<div class="alt-text-section">'
                '<div class="field-label" style="color:#c0392b;">Error generating alt text</div>'
                '<div style="background:#fdf2f2;border:1px solid #f5c6cb;border-radius:4px;'
                'padding:10px 12px;font-size:13px;color:#922b21;">' + error_msg + '</div>'
                '</div>'
            )
        else:
            html += (
                '<div class="alt-text-section">'
                '<div class="field-label">'
                'Alt Text'
                '<span class="edit-badge" id="edit-badge-' + str(record_id) + '" style="display:none;">Edited</span>'
                '</div>'
                '<textarea class="alt-text-input" id="alttext-' + str(record_id) + '"'
                ' oninput="autoResize(this); onAltTextChange(' + str(record_id) + ')">'
                + self.esc(alt_text) +
                '</textarea>'
                '</div>'
                '<div class="record-actions">'
                '<button class="approve-btn" onclick="approveRecord(' + str(record_id) + ')">✓ Approve</button>'
                '<button class="restore-btn" onclick="restoreOriginal(' + str(record_id) + ')">↩ Restore Original</button>'
                '</div>'
            )

        # Notes
        html += (
            '<div class="notes-section">'
            '<div class="field-label">Reviewer Notes</div>'
            '<textarea class="notes-input" id="notes-' + str(record_id) + '"'
            ' placeholder="Optional notes..."'
            ' oninput="saveNotes(' + str(record_id) + ', this.value)"></textarea>'
            '</div>'
            '</div>'
        )

        return html

    # -----------------------------------------------------------------------
    # Page generation
    # -----------------------------------------------------------------------

    def build_index_page(self, total_pages, page_count_per_page):
        """Build the index HTML page."""
        model = self.summary.get('model', 'unknown')
        provider = self.summary.get('provider', 'unknown')
        total = len(self.results)

        html = (
            '<!DOCTYPE html><html lang="en"><head>'
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Alt Text Review — ' + self.esc(self.folder_name) + '</title>'
            '<style>' + self.get_css() + '</style>'
            '<script>' + self.get_javascript() + '</script>'
            '</head>'
            '<body data-total-records="' + str(total) + '">'
        )

        html += (
            '<div class="header">'
            '<h1>Alt Text Review</h1>'
            '<p>' + self.esc(self.folder_name) + '</p>'
            '<p>Provider: ' + self.esc(provider.upper()) + ' &nbsp;|&nbsp; Model: ' + self.esc(model) + '</p>'
            '</div>'
        )

        html += (
            '<div class="progress-bar-wrap">'
            '<div class="progress-label" id="progress-text">0 / ' + str(total) + ' approved</div>'
            '<div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>'
            '</div>'
        )

        html += (
            '<div class="summary-grid">'
            '<div class="summary-card"><div class="number">' + str(total) + '</div>'
            '<div class="label">Total Images</div></div>'
            '<div class="summary-card"><div class="number">' + str(total_pages) + '</div>'
            '<div class="label">Review Pages</div></div>'
            '<div class="summary-card"><div class="number">' + str(page_count_per_page) + '</div>'
            '<div class="label">Images per Page</div></div>'
            '</div>'
        )

        html += (
            '<div class="export-bar">'
            '<button class="export-btn" onclick="exportDecisions()">Export Decisions →</button>'
            '<span class="export-note">Review images on each page below, then export your decisions.</span>'
            '</div>'
        )

        html += '<div class="page-links">'
        for p in range(1, total_pages + 1):
            start = (p - 1) * page_count_per_page + 1
            end = min(p * page_count_per_page, total)
            html += (
                '<a class="page-link" href="review_page_' + str(p) + '.html">'
                'Page ' + str(p) + '<br>'
                '<span style="font-size:12px;font-weight:400;">Images ' + str(start) + '–' + str(end) + '</span>'
                '</a>'
            )
        html += '</div>'

        html += '</body></html>'
        return html

    def build_review_page(self, page_num, records_slice, total_pages, total_records):
        """Build a single review HTML page."""
        first_id = records_slice[0][0]
        last_id = records_slice[-1][0]

        html = (
            '<!DOCTYPE html><html lang="en"><head>'
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Review Page ' + str(page_num) + ' — ' + self.esc(self.folder_name) + '</title>'
            '<style>' + self.get_css() + '</style>'
            '<script>' + self.get_javascript() + '</script>'
            '</head>'
            '<body data-total-records="' + str(total_records) + '">'
        )

        html += (
            '<div class="header">'
            '<h1>Alt Text Review — Page ' + str(page_num) + ' of ' + str(total_pages) + '</h1>'
            '<p>' + self.esc(self.folder_name) + '</p>'
            '</div>'
        )

        html += (
            '<div class="progress-bar-wrap">'
            '<div class="progress-label" id="progress-text">0 / ' + str(total_records) + ' approved</div>'
            '<div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>'
            '</div>'
        )

        # Navigation
        prev_link = (
            ('review_page_' + str(page_num - 1) + '.html' if page_num > 1 else '#')
        )
        next_link = (
            ('review_page_' + str(page_num + 1) + '.html' if page_num < total_pages else '#')
        )
        prev_class = 'nav-btn' + ('' if page_num > 1 else ' disabled')
        next_class = 'nav-btn' + ('' if page_num < total_pages else ' disabled')

        html += (
            '<div class="navigation">'
            '<a href="review_index.html" class="nav-btn">Index</a>'
            '<a href="' + prev_link + '" class="' + prev_class + '">← Previous</a>'
            '<span style="margin:0 12px;font-size:13px;color:#666;">Page ' + str(page_num) + ' of ' + str(total_pages) + '</span>'
            '<a href="' + next_link + '" class="' + next_class + '">Next →</a>'
            '</div>'
        )

        html += (
            '<div class="export-bar">'
            '<button class="export-btn" onclick="exportDecisions()">Export Decisions →</button>'
            '<span class="export-note">Images ' + str(first_id) + '–' + str(last_id) + ' of ' + str(total_records) + '</span>'
            '</div>'
        )

        for record_id, rec in records_slice:
            html += self.record_html(rec, record_id)

        # Bottom navigation
        html += (
            '<div class="navigation" style="margin-top:20px;">'
            '<a href="review_index.html" class="nav-btn">Index</a>'
            '<a href="' + prev_link + '" class="' + prev_class + '">← Previous</a>'
            '<span style="margin:0 12px;font-size:13px;color:#666;">Page ' + str(page_num) + ' of ' + str(total_pages) + '</span>'
            '<a href="' + next_link + '" class="' + next_class + '">Next →</a>'
            '</div>'
        )

        html += '</body></html>'
        return html

    # -----------------------------------------------------------------------
    # Main run
    # -----------------------------------------------------------------------

    def run(self):
        print("\n" + "=" * 60)
        print("Alt Text HTML Review Builder")
        print("=" * 60)
        print("Folder: " + self.folder_name)

        print("\n1. Loading alt text results...")
        if not self.load_json():
            return False

        print("\n2. Setting up review folder...")
        if not self.create_review_folder():
            return False

        print("\n3. Copying images...")
        self.copy_images()

        total = len(self.results)
        total_pages = max(1, (total + self.records_per_page - 1) // self.records_per_page)

        print("\n4. Generating HTML pages...")

        # Build paginated review pages
        for page_num in range(1, total_pages + 1):
            start = (page_num - 1) * self.records_per_page
            end = min(start + self.records_per_page, total)
            # records_slice: list of (1-based record_id, record_dict)
            records_slice = [(start + i + 1, self.results[start + i]) for i in range(end - start)]

            page_html = self.build_review_page(page_num, records_slice, total_pages, total)
            page_path = os.path.join(self.review_folder, "review_page_" + str(page_num) + ".html")
            with open(page_path, 'w', encoding='utf-8') as f:
                f.write(page_html)

        # Build index page
        index_html = self.build_index_page(total_pages, self.records_per_page)
        index_path = os.path.join(self.review_folder, "review_index.html")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)

        print("Generated " + str(total_pages) + " review page(s) + index")

        print("\n" + "=" * 60)
        print("DONE")
        print("=" * 60)
        print("Open in browser: " + index_path)
        print("\nWorkflow:")
        print("  1. Open review_index.html in your browser")
        print("  2. Review each image — edit alt text or click Approve")
        print("  3. Click 'Export Decisions' and save the JSON file")
        print("  4. Move the JSON file to: " + os.path.join(self.review_folder, "exports/"))
        print("  5. Run: python integrate_edits.py")
        print("=" * 60)
        return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate HTML review interface for alt text results.'
    )
    parser.add_argument(
        '--folder', '-f',
        help='Path to an AltText_ output folder (defaults to newest).'
    )
    parser.add_argument(
        '--records-per-page', '-n',
        type=int, default=10,
        help='Images per review page (default: 10).'
    )
    args = parser.parse_args()

    base_output_dir = os.path.join(script_dir, "output_folders")

    if args.folder:
        folder_path = args.folder
        if not os.path.isdir(folder_path):
            print("Error: folder not found: " + folder_path)
            return 1
    else:
        folder_path = prompt_for_folder(base_output_dir)
        if not folder_path:
            return 1

    builder = AltTextHTMLReviewBuilder(folder_path, records_per_page=args.records_per_page)
    return 0 if builder.run() else 1


if __name__ == "__main__":
    sys.exit(main())
