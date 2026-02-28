"""
AI model try-on via GrsAI nano-banana-pro-vt.

Goal: Generate a new e-commerce fashion shot with:
  - A specified Asian male model (face + pose from TARGET_MODEL_URL)
  - Clothing faithfully reproduced from the flat garment image
  - Texture/detail fidelity from the detail image
  - Clean studio background (optionally referenced by BACKGROUND_URL)

Usage:
    1. Fill GRSAI_API_KEY below.
    2. Set TARGET_MODEL_URL to an Asian male model photo with the pose you want.
    3. Optionally set BACKGROUND_URL.
    4. Run:
       python ops/run_ai_image_generate.py

Input order for nano-banana-pro-vt (img_n reference in prompt):
    img_1 = TARGET model (face + pose anchor) — NOT the original garment model
    img_2 = flat garment image (clothing structure)
    img_3 = detail image (fabric texture, stitching, logo, zips)
    img_4 = background reference (optional)
"""
import os
import sys
import requests

# Ensure project root is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.ai_image import GrsAIClient

# ============================================================
# Config
# ============================================================

GRSAI_API_KEY = "sk-cb2fd749b4f749198a491588a87375ed"

# GrsAI relay host. Keep this unless your account requires another host.
GRSAI_HOST = "https://grsaiapi.com"

# img_1: Target Asian male model — provides face identity + pose anchor.
# Replace this URL with the actual reference photo you want to use.
TARGET_MODEL_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/468n73j2sSJIbfZvsIZvDpvUaS8.webp"

# img_2: Flat garment image — defines clothing structure and silhouette.
# img_3: Detail / texture closeup — fabric, stitching, logo, zips, quilting.
GARMENT_URLS = {
    "flat":   "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2503BK71_7.jpg",
    "detail": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2503BK71_5.jpg",
}

# img_4 (optional): Background reference image.
# Set to None to let the model use a plain studio background.
BACKGROUND_URL = None

# Original garment model shots kept as reference only — NOT sent in the API call.
ORIGINAL_MODEL_REFS = {
    "front_1": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2503BK71_1.jpg",
    "front_2": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2503BK71_2.jpg",
    "back":    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2503BK71_3.jpg",
}

MODEL = "nano-banana-pro-vt"
ASPECT_RATIO = "3:4"
IMAGE_SIZE = "1K"

# Prompt uses explicit img_n references to separate role of each input image.
# img_1 = target model (face + pose), img_2 = garment flat, img_3 = texture detail
#
# "Structural Integrity" mode: designed for batch e-commerce use where garment
# fidelity must match the original product exactly (buttons, spacing, pockets,
# zips, seams). Do NOT normalise or average any layout — copy exactly as-is.
PROMPT = (
    "Task: High-fidelity virtual try-on with zero structural deviation. "
    "1. Identity & Pose: Use the exact model identity and body pose from img_1. "
    "Do NOT use the face or pose from the original garment photos. "
    "2. Garment Reconstruction: Dress the model with the garment from img_2. "
    "Preserve the original garment's exact silhouette, cut, and proportions — do not alter the design. "
    "3. Structural Integrity: STRICTLY preserve the layout of every functional detail — "
    "including the EXACT number, SIZE, and NON-UNIFORM SPACING of buttons, pockets, zippers, flaps, and seams. "
    "Do NOT normalise, average, or redistribute their positions. Copy them exactly as they appear in img_2. "
    "4. Material & Texture: Replicate micro-texture, fabric luster, quilting pattern, stitching lines, "
    "logo placement, and all surface details from img_3 with pixel-level fidelity. "
    "5. Fit & Drape: Ensure the garment fits the model naturally, with realistic folds and drape "
    "that reflect the model's pose, while maintaining 100% fidelity to the original design. "
    "6. Background: Clean professional studio lighting, plain or minimally textured background"
    + (" similar to img_4." if BACKGROUND_URL else ".")
    + " Output: 8K resolution, realistic fashion photography."
)

SAVE_PATH = r"D:\images\output\MWX2503BK71_result.jpg"

# ============================================================
# Main
# ============================================================


def main():
    if not GRSAI_API_KEY or GRSAI_API_KEY == "PASTE_YOUR_GRSAI_API_KEY_HERE":
        raise ValueError("Please paste your GrsAI API key into GRSAI_API_KEY before running.")
    if not TARGET_MODEL_URL or TARGET_MODEL_URL == "PASTE_TARGET_ASIAN_MODEL_URL_HERE":
        raise ValueError("Please set TARGET_MODEL_URL to your target Asian male model photo URL.")

    # img_1 = target model (face + pose), img_2 = flat garment, img_3 = texture detail
    urls = [
        TARGET_MODEL_URL,
        GARMENT_URLS["flat"],
        GARMENT_URLS["detail"],
    ]
    if BACKGROUND_URL:
        urls.append(BACKGROUND_URL)  # img_4 = background reference

    print("=== Input images (in img_n order) ===")
    labels = ["img_1 (target model)", "img_2 (flat garment)", "img_3 (texture detail)", "img_4 (background)"]
    for label, url in zip(labels, urls):
        print(f"  {label}: {url}")

    print("\n=== Original garment model refs (not sent to API) ===")
    for name, url in ORIGINAL_MODEL_REFS.items():
        print(f"  {name}: {url}")

    print("\n=== Submit generation task ===")
    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    result_url = client.generate_and_wait(
        urls=urls,
        prompt=PROMPT,
        model=MODEL,
        aspect_ratio=ASPECT_RATIO,
        image_size=IMAGE_SIZE,
    )

    if not result_url:
        print("[ERROR] Image generation failed. Check logs above.")
        return

    if SAVE_PATH:
        os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
        img_data = requests.get(result_url, timeout=60).content
        with open(SAVE_PATH, "wb") as f:
            f.write(img_data)
        print(f"\nSaved result: {SAVE_PATH}")
    else:
        print(f"\nResult image URL: {result_url}")


if __name__ == "__main__":
    main()
