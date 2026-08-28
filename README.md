# Alt Text Pipeline

A three-step pipeline for generating AI-assisted alt text for archival image collections. Supports Claude, OpenAI, and Gemini. First and foremost, archivists can generate alt text quickly and relatively cheaply.  They can also edit those outputs in a custom HTML interface and quickly integrate their decisions back into output files while also preserving a record of edits made. In addition, archivists can choose to run the calibration step, which allows them to easily customize collection-specific examples and a style guide to be included in the image analysis prompt.

## How it works

**Step 0 — Calibration** (`step-0-calibration.py`)
Process a sample of collection images (default: 2). The results then become a baseline to review and correct. Corrections become few-shot examples that guide the full run, and the AI will analyze the edits to derive a collection-specific style guide. This style guide and the examples are in a text file that lives in the collection images folder and can also be reviewed and edited before running on a larger portion of the collection.

**Step 1 — Image Analysis** (`step-1-image-analysis.py`, run via `run.py`)
Generates alt text for all images in the collection. If calibration examples and style guide have been created, they are sent as part of the prompt, and applied to every image.

**Step 2 — HTML Review** (`step-2-html-review.py`)
Generates a browser-based review interface. Each image can be viewed at full size, text can be edited, and internal archivist notes can be added. Export decisions as JSON when done.

**Integrate Edits** (`integrate_edits.py`)
Applies reviewer decisions back into the results JSON when used on a full run. To process calibration decisions and write `collection-examples.txt` to the image folder, use `step-0-calibration.py --export` — this includes both the few-shot examples and the AI-generated style guide. Both can be reviewed and edited before running step 1.

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or with uv:

```bash
uv sync
```

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY=...   # for Claude
export OPENAI_API_KEY=...      # for OpenAI
export GEMINI_API_KEY=...      # for Gemini
```

### 3. Configure

Edit [config.py](config.py):

- `IMAGE_FOLDER` — path to your image folder (relative to project root)
- `STEP1_PROVIDER` — `"claude"`, `"openai"`, or `"gemini"`
- `STEP1_MODEL` — set to `None` to use the provider's default

```bash
python run.py --config   # preview current settings
```

### 4. Run the pipeline

**Recommended: start with a calibration run**

```bash
# Step 0: process a small sample
python step-0-calibration.py

# Step 2: open the review interface
python step-2-html-review.py

# In browser: review, edit, export decisions JSON → move to review/exports/

# Integrate edits and write calibration examples
python step-0-calibration.py --export

# Step 1: full run with style-guided examples
python run.py
```

**Or skip calibration and run directly:**

```bash
python run.py
```

**Optional: verify the style guide before the full run**

```bash
# After step-0-calibration.py --export, test the style guide on a few fresh images
python step-0-calibration.py --test
# Review the output, edit collection-examples.txt if needed, then re-test or run.py
```

---

## Calibration and the full run

By default (`SKIP_CALIBRATION_IMAGES = 2` in `config.py`), the full run skips the first N images in the folder and only processes the rest. Skipped images are not included in the output — they have already been reviewed and live in the calibration output folder. Increase the count if you have also done test runs whose images you want to exclude (e.g. `SKIP_CALIBRATION_IMAGES = 4` to skip 2 calibration + 2 test images).

Set `SKIP_CALIBRATION_IMAGES = 0` to process every image in the folder.

---

## Collection context and examples

Place these optional files in your image folder to guide the AI:

**`collection-context.txt`** — a brief description of the collection (provenance, date range, subject matter). Included in every prompt.

**`collection-examples.txt`** — few-shot examples showing original AI output alongside archivist corrections. Generated automatically by `step-0-calibration.py --export`, or written by hand. Format:

```
Image: filename.jpg
Original: AI-generated alt text here
Alt Text: archivist's corrected version here
```

---

## Batching

Set `IMAGES_PER_CALL` in [config.py](config.py) to send multiple images per API call — useful for documents with a front and back, or when images naturally pair together. All three providers support multi-image calls.

Set `RELATIONSHIP_BETWEEN_IMAGES_PER_CALL` to a short sentence describing how images in each batch relate to one another (e.g. `"These two images are front and back of the same sketch."`). Leave it empty if the images in a batch are unrelated.

---

## Multiple folders

Set `IMAGE_FOLDERS` in [config.py](config.py) to process several folders in one run:

```python
IMAGE_FOLDERS = ["images/box-1", "images/box-2", "images/box-3"]
```

---

## Output

Results are written to `output_folders/AltText_<slug>_<timestamp>/`:

```
output_folders/
  AltText_.../
    metadata/
      json/
        alt_text_results.json
        edit_report.json        (after integrate_edits.py)
    review/
      review_index.html
      review_page_1.html
      images/
      exports/
```

---

## Optional: Portkey gateway

To route API calls through [Portkey](https://portkey.ai) for logging and cost tracking, set `USE_PORTKEY = True` in [config.py](config.py) and provide:

```bash
export PORTKEY_API_KEY=...
export PORTKEY_VIRTUAL_KEY=...
```

---

## Requirements

- Python 3.10+
- `anthropic`, `openai`, `google-genai`, `pillow`, `tenacity`, `portkey-ai`

TIFF images are automatically converted to JPEG before sending to the API.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with assistance of Claude (Anthropic).*
