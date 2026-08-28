# config.py
"""
Configuration for the alt-text-pipeline.
Edit this file to set your provider, model, and image folder preferences.
"""

# =============================================================================
# IMAGE FOLDER CONFIGURATION
# =============================================================================
# Option 1: Process a SINGLE folder (path relative to project root)
IMAGE_FOLDER = "images/junge"

# Option 2: Process MULTIPLE folders sequentially
# When set (not None/empty), takes precedence over IMAGE_FOLDER
IMAGE_FOLDERS = None  # e.g., ["images/small", "images/medium", "images/large"]

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================
# Provider options: "claude", "openai", "gemini"
STEP1_PROVIDER = "gemini"

# Set a specific model, or None to use the provider's default
STEP1_MODEL = None

# =============================================================================
# AVAILABLE MODELS BY PROVIDER
# =============================================================================
AVAILABLE_MODELS = {
    # -------------------------------------------------------------------------
    # ANTHROPIC CLAUDE MODELS
    # -------------------------------------------------------------------------
    "claude": {
        "default": "claude-sonnet-4-6",
        "models": [
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ]
    },

    # -------------------------------------------------------------------------
    # OPENAI MODELS
    # -------------------------------------------------------------------------
    "openai": {
        "default": "gpt-5.6-luna",
        "models": [
            "gpt-5.6-sol",           
            "gpt-5.6-terra",     
            "gpt-5.6-luna",      
            "gpt-5.5-pro",
            "gpt-5.5",           
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-4.1",           
            "gpt-4.1-mini",
            "gpt-4o",            
            "gpt-4o-mini",          
        ]
    },

    # -------------------------------------------------------------------------
    # GOOGLE GEMINI MODELS
    # -------------------------------------------------------------------------
    "gemini": {
        "default": "gemini-3.5-flash-lite",
        "models": [
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
    }
}

# =============================================================================
# PIPELINE STEPS
# =============================================================================
# Set True to automatically run Step 2 (HTML Review) after each folder.
RUN_HTML_REVIEW = True

# =============================================================================
# IMAGES PER CALL
# =============================================================================
# Number of images to send in a single API call (i.e. message).
# Claude, OpenAI, and Gemini all support multiple images per call.
IMAGES_PER_CALL = 6

# When IMAGES_PER_CALL > 1, this sentence is added to the prompt so the AI
# knows how the images in each batch relate to one another.
# Leave empty ("") if the images in a batch are unrelated.
# Example: "These two images are front and back of the same sketch."
RELATIONSHIP_BETWEEN_IMAGES_PER_CALL = "These two images are from the same collection. They are in order, front and then back of each image one after the other."

# =============================================================================
# CALIBRATION CONFIGURATION
# =============================================================================
# Number of images processed by step-0-calibration.py to create the calibration set.
# After review and editing, these become few-shot examples for the full run.
CALIBRATION_COUNT = 2

# Number of images used in calibration test mode (step-0-calibration.py --test).
# Run this after calibration is complete and collection-examples.txt has been created
# to verify the style guide before a full run.
CALIBRATION_TEST_COUNT = 2

# When True, test mode skips the first CALIBRATION_COUNT images (the ones already
# used to create the examples) and tests on fresh images from the collection.
CALIBRATION_TEST_SKIP_CALIBRATION = True

# Number of images to skip at the start of the full run (run.py).
# Skipped images are not re-processed; those in collection-examples.txt carry
# their archivist-reviewed alt text forward. Increase this count if you have
# done test runs whose images you also want to exclude from the full run.
# Set to 0 to re-process every image.
SKIP_CALIBRATION_IMAGES = 0

# =============================================================================
# PORTKEY GATEWAY CONFIGURATION
# =============================================================================
# Set True to route API calls through Portkey (requires PORTKEY_API_KEY
# and PORTKEY_VIRTUAL_KEY environment variables).
USE_PORTKEY = True

# =============================================================================
# STEP 1 PROMPT
# =============================================================================
# {collection_context} is replaced at runtime with the contents of
# collection-context.txt found in the image folder, or an empty string if
# no such file exists.
STEP1_PROMPT = """\
Analyze this image and generate accurate alt text for accessibility purposes. 
{collection_context}
{collection_examples}
Respond in this exact format with no additional text before or after:

Alt Text: [one plain sentence for a screen reader — state what the image shows without saying "image of". Include relevant details including date, title (in original language), author if visible. Do not mention materials used to create an object unless explicitly noted in the image.]

"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_image_folders():
    if IMAGE_FOLDERS:
        return IMAGE_FOLDERS
    return [IMAGE_FOLDER]


def get_step1_config(image_folder=None):
    provider = STEP1_PROVIDER.lower()
    if provider not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(AVAILABLE_MODELS.keys())}")
    model = STEP1_MODEL if STEP1_MODEL else AVAILABLE_MODELS[provider]["default"]
    folder = image_folder if image_folder else IMAGE_FOLDER
    return {
        "provider": provider,
        "model": model,
        "image_folder": folder,
        "use_portkey": USE_PORTKEY,
        "images_per_call": IMAGES_PER_CALL,
    }


def print_current_config():
    print("\n" + "=" * 55)
    print("CURRENT CONFIGURATION")
    print("=" * 55)
    folders = get_image_folders()
    if len(folders) == 1:
        print(f"Image Folder : {folders[0]}")
    else:
        print(f"Image Folders ({len(folders)}):")
        for f in folders:
            print(f"  - {f}")
    step1 = get_step1_config()
    print(f"\nStep 1 — Image Analysis:")
    print(f"  Provider : {step1['provider'].upper()}")
    print(f"  Model    : {step1['model']}")
    print(f"  Batch    : {step1['images_per_call']} image(s) per call")
    from pipeline_core import portkey_active
    if portkey_active(step1["provider"], step1["use_portkey"]):
        print(f"  Gateway  : Portkey")
    print(f"\nStep 2 — HTML Review : {'enabled' if RUN_HTML_REVIEW else 'disabled'}")
    print(f"Calibration sample     : {CALIBRATION_COUNT} images (run step-0-calibration.py)")
    skip_label = f"skip first {SKIP_CALIBRATION_IMAGES} image(s)" if SKIP_CALIBRATION_IMAGES else "re-process all images"
    print(f"Full run             : {skip_label}")
    print("=" * 55 + "\n")


def list_available_models(provider=None):
    targets = {provider.lower(): AVAILABLE_MODELS[provider.lower()]} if provider else AVAILABLE_MODELS
    for prov, cfg in targets.items():
        print(f"\n{prov.upper()} Models:")
        print(f"  Default: {cfg['default']}")
        print("  Available:")
        for m in cfg["models"]:
            print(f"    - {m}")


if __name__ == "__main__":
    print_current_config()
    print("AVAILABLE MODELS:")
    list_available_models()
