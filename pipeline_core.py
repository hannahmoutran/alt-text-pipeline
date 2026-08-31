#!/usr/bin/env python3
"""
Alt Text Pipeline — Core utilities shared across pipeline scripts.
"""

import os
import base64
import logging
import re
import time
from io import BytesIO

from PIL import Image as PILImage
import tenacity


FIELD_MAPPING = {
    'alt text': 'alt_text'
}

STYLE_ANALYSIS_PROMPT = """\
Below are calibration examples from this archival collection. Each shows the original \
AI-generated alt text alongside the archivist's correction.

{examples_text}

Based on these corrections, write a concise style guide (4–8 bullet points) capturing:
- Information the archivist consistently added
- Information the AI included that the archivist removed or changed
- Vocabulary, terminology, naming conventions, etc. specific to this collection
- Preferred level of detail and descriptive approach

Format your response as:
Style Guide for this Collection:
• [point]
• [point]
...

Be specific, concrete, and succinct — this style guide will guide alt text generation for the rest of the collection.\
"""


# =============================================================================
# COLLECTION CONTEXT
# =============================================================================

def load_style_guide(folder_path):
    examples_file = os.path.join(folder_path, "collection-examples.txt")
    if not os.path.isfile(examples_file):
        return ""
    try:
        with open(examples_file, 'r', encoding='utf-8') as f:
            content = f.read()
        marker = "# Style Guide"
        idx = content.find(marker)
        if idx == -1:
            return ""
        style_guide = content[idx + len(marker):].lstrip('\n').strip()
        if style_guide:
            logging.info(f"Loaded style guide from: {examples_file}")
        return style_guide
    except Exception as e:
        logging.warning(f"Could not read style guide from collection-examples.txt: {e}")
        return ""


def write_style_guide(folder_path, style_guide):
    """Write (or replace) the '# Style Guide' section of collection-examples.txt.

    Everything above the marker — the calibration examples — is left untouched,
    so a hand-edited examples file keeps its edits.
    """
    examples_file = os.path.join(folder_path, "collection-examples.txt")
    if not os.path.isfile(examples_file):
        logging.warning(f"No collection-examples.txt found in: {folder_path}")
        return False
    try:
        with open(examples_file, 'r', encoding='utf-8') as f:
            content = f.read()
        marker = "# Style Guide"
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx]
        content = content.rstrip('\n')
        with open(examples_file, 'w', encoding='utf-8') as f:
            f.write(f"{content}\n\n{marker}\n{style_guide.strip()}\n")
        return True
    except Exception as e:
        logging.warning(f"Could not write style guide to collection-examples.txt: {e}")
        return False


def load_collection_context(folder_path):
    context_file = os.path.join(folder_path, "collection-context.txt")
    if not os.path.isfile(context_file):
        return ""
    try:
        with open(context_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            return ""
        logging.info(f"Loaded collection context from: {context_file}")
        context_text = "\n".join(lines)
        return (
            f"[Collection Context]\n"
            f"The following background applies to the entire collection. "
            f"Use it to inform your alt text where relevant.\n"
            f"{context_text}"
        )
    except Exception as e:
        logging.warning(f"Could not read collection context: {e}")
        return ""


# =============================================================================
# IMAGE PREPARATION
# =============================================================================

def prepare_image(image_path):
    """Return (image_bytes, media_type). Converts TIFF to JPEG."""
    ext = os.path.splitext(image_path)[1].lower()
    if ext in ('.tif', '.tiff'):
        img = PILImage.open(image_path)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=95)
        return buf.getvalue(), 'image/jpeg'
    media_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'
    }
    with open(image_path, 'rb') as f:
        return f.read(), media_types.get(ext, 'image/jpeg')


# =============================================================================
# RESPONSE PARSING
# =============================================================================

def parse_response(raw_response):
    """Parse key-value LLM response into a dict. Returns (dict, error)."""
    if not raw_response or not raw_response.strip():
        return None, "Empty response"

    result = {}
    current_key = None
    current_lines = []

    for line in raw_response.split('\n'):
        cleaned = re.sub(r'^#+\s*', '', line.strip())
        cleaned = re.sub(r'^\*+\s*', '', cleaned)
        cleaned = re.sub(r'\*+', '', cleaned)
        cleaned_lower = cleaned.lower()

        found = False
        for display_name, dict_key in FIELD_MAPPING.items():
            if cleaned_lower.startswith(display_name + ':'):
                if current_key:
                    result[current_key] = ' '.join(current_lines).strip()
                current_key = dict_key
                value_start = cleaned_lower.find(display_name + ':') + len(display_name) + 1
                current_lines = [cleaned[value_start:].strip()]
                found = True
                break

        if not found and current_key and line.strip():
            stripped = line.strip()
            if not stripped.startswith('#'):
                current_lines.append(stripped)

    if current_key:
        result[current_key] = ' '.join(current_lines).strip()

    if not result:
        return None, "No recognized fields found in response"
    return result, None


def build_batch_prompt(base_prompt, n_images, relationship=""):
    """Adapt prompt for n_images > 1."""
    if n_images == 1:
        return base_prompt
    prompt = base_prompt.replace("this image", f"each of these {n_images} images", 1)
    if relationship:
        first_newline = prompt.find("\n")
        if first_newline != -1:
            prompt = prompt[:first_newline + 1] + relationship + "\n" + prompt[first_newline + 1:]
        else:
            prompt = prompt + "\n" + relationship
    marker = "Respond in this exact format with no additional text before or after:"
    idx = prompt.find(marker)
    if idx != -1:
        numbered = "\n".join(f"Alt Text {i+1}: [alt text for image {i+1}]" for i in range(n_images))
        prompt = prompt[:idx] + f"{marker}\n\n{numbered}\n"
    return prompt


def parse_batch_response(raw_response, n_images):
    """Extract Alt Text 1:, Alt Text 2:, … from a batched response."""
    results = [{'alt_text': ''} for _ in range(n_images)]
    for i in range(1, n_images + 1):
        pattern = re.compile(rf'Alt\s+Text\s+{i}\s*:\s*(.+)', re.IGNORECASE)
        match = pattern.search(raw_response)
        if not match:
            continue
        start = match.start(1)
        if i < n_images:
            next_pat = re.compile(rf'Alt\s+Text\s+{i+1}\s*:', re.IGNORECASE)
            next_match = next_pat.search(raw_response, start)
            end = next_match.start() if next_match else len(raw_response)
        else:
            end = len(raw_response)
        results[i - 1] = {'alt_text': raw_response[start:end].strip()}
    return results


# =============================================================================
# API CLIENTS
# =============================================================================

# Providers that actually route through Portkey when USE_PORTKEY is set.
# Claude and Gemini always call their native SDKs directly, so USE_PORTKEY
# has no effect for them.
PORTKEY_SUPPORTED_PROVIDERS = {'openai'}


def portkey_active(provider, use_portkey):
    """True only when calls for this provider actually route through Portkey."""
    return bool(use_portkey) and provider in PORTKEY_SUPPORTED_PROVIDERS


def init_client(provider, use_portkey=False):
    if provider == 'claude':
        import anthropic
        api_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        return anthropic.Anthropic(api_key=api_key)
    elif provider == 'openai':
        if portkey_active(provider, use_portkey):
            from portkey_ai import Portkey
            return Portkey(
                api_key=os.getenv('PORTKEY_API_KEY'),
                virtual_key=os.getenv('PORTKEY_VIRTUAL_KEY')
            )
        from openai import OpenAI
        return OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    elif provider == 'gemini':
        from google import genai
        return genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    else:
        raise ValueError(f"Unknown provider: {provider}")


# =============================================================================
# PROVIDER-SPECIFIC API CALLS
# =============================================================================

def _is_transient_error(exc):
    """Retry only on transient failures — rate limits (429), server errors (5xx),
    timeouts, and dropped connections. Auth errors, invalid requests, and
    unknown-model errors fail fast with the provider's real message instead of
    being retried and buried in a RetryError."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "overloaded"))


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception(_is_transient_error)
)
def _call_claude(client, image_paths, model_name, prompt):
    content = []
    for image_path in image_paths:
        image_bytes, media_type = prepare_image(image_path)
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}})
    content.append({"type": "text", "text": prompt})
    response = client.messages.create(
        model=model_name,
        max_tokens=1500 * len(image_paths),
        messages=[{"role": "user", "content": content}]
    )
    raw = response.content[0].text.strip()
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return raw, usage


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception(_is_transient_error)
)
def _call_openai(client, image_paths, model_name, prompt):
    content = [{"type": "text", "text": prompt}]
    for image_path in image_paths:
        image_bytes, _ = prepare_image(image_path)
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}})
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": content}],
        max_completion_tokens=1500 * len(image_paths),
    )
    raw = response.choices[0].message.content.strip()
    usage = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
    return raw, usage


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception(_is_transient_error)
)
def _call_gemini(client, image_paths, model_name, prompt):
    from google.genai import types
    parts = []
    for image_path in image_paths:
        image_bytes, media_type = prepare_image(image_path)
        parts.append(types.Part(inline_data=types.Blob(mime_type=media_type, data=image_bytes)))
    parts.append(types.Part(text=prompt))
    response = client.models.generate_content(
        model=model_name,
        contents=[types.Content(parts=parts)],
        config=types.GenerateContentConfig(max_output_tokens=1500 * len(image_paths))
    )
    raw = response.text.strip()
    input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
    output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return raw, usage


def process_image(provider, client, image_paths, model_name, prompt, relationship=""):
    """Dispatch to the correct provider. Returns (parsed_list, raw, usage, time)."""
    start = time.time()
    n = len(image_paths)
    batch_prompt = build_batch_prompt(prompt, n, relationship)

    if provider == 'claude':
        raw, usage = _call_claude(client, image_paths, model_name, batch_prompt)
    elif provider == 'openai':
        raw, usage = _call_openai(client, image_paths, model_name, batch_prompt)
    elif provider == 'gemini':
        raw, usage = _call_gemini(client, image_paths, model_name, batch_prompt)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    processing_time = time.time() - start

    if n == 1:
        parsed, error = parse_response(raw)
        if not parsed:
            raise Exception(f"Parse failed: {error} | Raw: {raw[:200]}")
        parsed.setdefault('alt_text', "")
        return [parsed], raw, usage, processing_time
    else:
        parsed_list = parse_batch_response(raw, n)
        if not any(p.get('alt_text') for p in parsed_list):
            raise Exception(f"Batch parse failed — no alt text found | Raw: {raw[:200]}")
        return parsed_list, raw, usage, processing_time


# =============================================================================
# CALIBRATION EXAMPLES
# =============================================================================

def read_examples_file(folder_path):
    """Read collection-examples.txt and return [{filename, original, alt_text}]."""
    examples_path = os.path.join(folder_path, "collection-examples.txt")
    if not os.path.isfile(examples_path):
        return []
    try:
        examples = []
        current = None
        with open(examples_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip()
                if line.startswith('#'):
                    continue
                if line.lower().startswith('image:'):
                    if current and current.get('alt_text'):
                        examples.append(current)
                    current = {'filename': line[6:].strip(), 'original': '', 'alt_text': ''}
                elif line.lower().startswith('original:') and current is not None:
                    current['original'] = line[9:].strip()
                elif line.lower().startswith('archivist correction:') and current is not None:
                    current['alt_text'] = line[len('archivist correction:'):].strip()
        if current and current.get('alt_text'):
            examples.append(current)
        return examples
    except Exception as e:
        logging.warning(f"Could not read examples file: {e}")
        return []


def format_examples_for_prompt(examples, style_analysis=""):
    """Format examples as a prompt block, optionally preceded by the style analysis."""
    if not examples:
        return ""
    lines = ["[Examples]"]
    guidance = (
        "IMPORTANT: These examples are a guide to STYLE, tone, and level of detail — "
        "not to specific content. The image you are describing is different from the "
        "examples. Specific details (colors, numbers, text, titles, dates, placement, "
        "subject matter) will differ, and may be absent entirely. Describe what you "
        "observe in the current image. Do not copy or assume details from the "
        "examples.\n"
    )
    if style_analysis:
        lines.append(style_analysis)
        lines.append("\n" + guidance)
        lines.append("Calibration examples that informed this style guide:\n")
    else:
        lines.append(
            "Here are examples from this collection showing the AI-generated alt text "
            "and the archivist's corrections. Study the differences to understand the "
            "required style and level of detail.\n"
        )
        lines.append(guidance)
    for ex in examples:
        lines.append(f"Image: {ex['filename']}")
        lines.append(f"AI generated: {ex['original']}")
        lines.append(f"Archivist correction: {ex['alt_text']}\n")
    return "\n".join(lines) + "\n"


def generate_style_analysis(examples, provider, client, model_name):
    """Call the AI with calibration examples and return a style guide string."""
    if not examples:
        return ""
    ex_lines = []
    for ex in examples:
        ex_lines.append(f"Image: {ex['filename']}")
        ex_lines.append(f"AI generated: {ex['original']}")
        ex_lines.append(f"Archivist correction: {ex['alt_text']}")
        ex_lines.append("")
    prompt = STYLE_ANALYSIS_PROMPT.format(examples_text="\n".join(ex_lines))
    try:
        if provider == 'claude':
            response = client.messages.create(
                model=model_name,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        elif provider == 'openai':
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,
            )
            return response.choices[0].message.content.strip()
        elif provider == 'gemini':
            from google.genai import types
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(max_output_tokens=2000)
            )
            return response.text.strip()
    except Exception as e:
        logging.warning(f"Style analysis failed: {e}")
        return ""
    return ""


# =============================================================================
# IMAGE COLLECTION
# =============================================================================

def collect_all_images(input_folder):
    """Return list of (folder_label, image_path) for all images in the folder tree."""
    extensions = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp')
    all_images = []

    def sort_key(fname):
        m = re.search(r'(\d+)', fname)
        return (int(m.group(1)) if m else 0, fname.lower())

    direct = [f for f in os.listdir(input_folder)
               if os.path.isfile(os.path.join(input_folder, f)) and f.lower().endswith(extensions)]
    if direct:
        label = os.path.basename(os.path.normpath(input_folder))
        for img in sorted(direct, key=sort_key):
            all_images.append((label, os.path.join(input_folder, img)))

    for subfolder in sorted(os.listdir(input_folder)):
        subfolder_path = os.path.join(input_folder, subfolder)
        if os.path.isdir(subfolder_path):
            imgs = [f for f in os.listdir(subfolder_path) if f.lower().endswith(extensions)]
            for img in sorted(imgs, key=sort_key):
                all_images.append((subfolder, os.path.join(subfolder_path, img)))

    return all_images


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def process_image_list(images, prompt, provider, client, model_name, images_per_call, display_total, display_offset=0, relationship=""):
    """Process a list of (folder_label, img_path) tuples. Returns (results, issues, input_tokens, output_tokens)."""
    results = []
    issues = []
    total_input_tokens = 0
    total_output_tokens = 0

    for batch_start in range(0, len(images), images_per_call):
        batch = images[batch_start:batch_start + images_per_call]
        img_paths = [p for _, p in batch]
        filenames = [os.path.basename(p) for p in img_paths]
        disp_start = display_offset + batch_start + 1
        disp_end = display_offset + batch_start + len(batch)

        if len(batch) == 1:
            print(f"[{disp_start}/{display_total}] {filenames[0]}")
        else:
            print(f"[{disp_start}-{disp_end}/{display_total}] {', '.join(filenames)}")

        try:
            parsed_list, raw, usage, proc_time = process_image(provider, client, img_paths, model_name, prompt, relationship)
            total_input_tokens += usage.get('input_tokens', 0)
            total_output_tokens += usage.get('output_tokens', 0)
            tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
            print(f"        OK — {tokens:,} tokens  ({proc_time:.1f}s)")

            for (folder_label, img_path), parsed in zip(batch, parsed_list):
                filename = os.path.basename(img_path)
                results.append({
                    "folder": folder_label,
                    "filename": filename,
                    "image_path": img_path,
                    "alt_text": parsed.get('alt_text', ''),
                    "raw_response": raw
                })

        except Exception as e:
            logging.error(f"Error processing {filenames}: {e}")
            print(f"        FAILED: {e}")
            for folder_label, img_path in batch:
                filename = os.path.basename(img_path)
                issues.append({"image_path": img_path, "filename": filename, "error": str(e)})
                results.append({
                    "folder": folder_label,
                    "filename": filename,
                    "image_path": img_path,
                    "alt_text": "",
                    "error": str(e),
                    "raw_response": ""
                })

        time.sleep(0.5)

    return results, issues, total_input_tokens, total_output_tokens
