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
from datetime import datetime

# Ensure project root is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.ai_image import GrsAIClient, upload_bytes_to_r2

# ============================================================
# Config
# ============================================================

GRSAI_API_KEY = "sk-cb2fd749b4f749198a491588a87375ed"

# GrsAI relay host. Keep this unless your account requires another host.
GRSAI_HOST = "https://grsaiapi.com"

# img_1: Target Asian male model — provides face identity + pose anchor.
# Replace this URL with the actual reference photo you want to use.
TARGET_MODEL_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/menmode_1_1.png"

# img_2: Front flat garment image — defines clothing structure and silhouette.
# img_3: Back flat image (optional) — helps model understand 3D garment shape.
#         Set to None if not available; detail image will take this slot instead.
# detail: Texture / closeup — fabric, stitching, logo, zips, quilting.
GARMENT_URLS = {
    "flat":   "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2343BL56_7.jpg",
    "back":   None,   # Optional: URL of back flat image, or None
    "detail": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2343BL56_4.jpg",
}

# Background reference image (optional). Set to None for plain studio background.
BACKGROUND_URL = None

# Original garment model shots kept as reference only — NOT sent in the API call.
ORIGINAL_MODEL_REFS = {
    "front_1": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2343BL56_1.jpg",
    "front_2": "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2343BL56_5.jpg",
    "back":    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/MWX2343BL56_3.jpgg",
}

MODEL = "nano-banana-pro-vt"
ASPECT_RATIO = "3:4"
IMAGE_SIZE = "1K"

# Neckline / closure style mode.  Choose one of:
#   "closed"  — 全闭合：高领、立领、拉链到顶的工装/冲锋衣（默认）
#   "relaxed" — 自然微张：翻领、Polo、卫衣，领口随平铺图角度自然打开
#   "layered" — 叠穿外套：开襟夹克/西装，前片自然敞开，内搭白 T 可见
STYLE_MODE = "relaxed"

# Negative prompt: explicitly exclude common AI generation errors.
# Applied when GrsAI API supports the negativePrompt field.
# NEGATIVE_PROMPT = (
#     "badge on sleeve, arm patch, shoulder logo, embroidery on arm, "
#     "extra pockets, extra zippers, asymmetric details not in reference, "
#     "evenly spaced buttons, modified collar, lowres, blurry, bad anatomy, "
#     "watermark, text, signature."
# )
NEGATIVE_PROMPT = (
    # 核心：封死"幻觉"装饰
    "badge on sleeve, arm patch, shoulder logo, embroidery on arm, arm brand label, "
    "extra pockets, extra zippers, asymmetric details not in reference, "
    # relaxed/layered 模式内里保护：防止领口翻开后乱加标牌或内衬花纹
    "inner labels, pattern on inner lining, extra inner buttons, "
    "fused garment layers, messy neckline, "
    # 核心：封死"扣子平均分布"和"领口变形"
    "evenly spaced buttons, symmetrically aligned buttons, modified collar, "
    "distorted neckline, "
    # 核心：画质与人体结构（防止模特崩坏）
    "lowres, blurry, bad anatomy, deformed fingers, extra limbs, "
    "watermark, text, signature, low quality, artifact."
)


def _build_prompt(garment_src: str, detail_src: str, bg_clause: str,
                  mode: str = "closed") -> str:
    """Build the generation prompt with correct img_n references.

    Args:
        garment_src:  img reference(s) for garment structure, e.g. "img_2" or
                      "img_2 (front) and img_3 (back)"
        detail_src:   img reference for texture detail, e.g. "img_3" or "img_4"
        bg_clause:    background sentence ending, e.g. "." or " similar to img_5."
        mode:         neckline/closure mode — "closed" | "relaxed" | "layered"
    """
    # ── Mode-specific neckline & closure instruction ──────────────────────
    if mode == "relaxed":
        # 翻领/Polo/卫衣：领口随平铺图原始角度自然打开
        neck_instr = (
            f"3. Neckline & Closure: NATURAL OPEN — replicate the EXACT collar opening angle "
            f"and zipper depth as shown in {garment_src}. "
            "Allow the collar to fold or stand naturally following the garment's cut. "
            "If the collar is partially open, show a simple white inner shirt at the opening. "
            "Do NOT force the collar closed or alter its original drape angle. "
        )
    elif mode == "layered":
        # 开襟外套/西装：前片自然敞开，内搭白 T 可见
        neck_instr = (
            f"3. Neckline & Layering: OPEN FRONT — the outer garment is worn open/unbuttoned "
            f"exactly as shown in {garment_src}. "
            "The lapels and front panels must follow the natural drape of the reference. "
            "Show a simple white inner shirt underneath; do NOT close the front opening. "
        )
    else:
        # closed（默认）：拉链到顶，高领贴合脖子
        neck_instr = (
            f"3. Neckline & Closure: FULLY CLOSED — MANDATORY to replicate the fully closed "
            f"zipper/collar state from {garment_src} with zero opening. "
            "The collar must fit snugly around the model's neck exactly as shown. "
            "Do NOT open the collar or lower the zipper. "
        )

    return (
        "Task: Industrial-grade high-fidelity virtual try-on. "
        "1. Identity & Face: STRICTLY and ONLY use the facial identity, skin tone, "
        "and head from img_1. "
        "ABSOLUTELY IGNORE any human features, faces, or bodies present in other reference images. "
        "The model in the output MUST be the person from img_1. "
        f"2. Strict Replication: Reconstruct the garment from {garment_src} with ZERO added details. "
        + neck_instr +
        "4. Anti-Hallucination: ABSOLUTELY PROHIBITED to add any logos, badges, patches, "
        "or decorative seams on sleeves, chest, or shoulders unless they are clearly present "
        f"in {garment_src}. "
        f"If a surface is smooth and plain in {garment_src}, "
        "it MUST be rendered as smooth and plain in the output. "
        f"5. Layout Fidelity: Maintain the exact non-uniform spacing of buttons, zippers, "
        f"and pocket positions from {garment_src}. Do NOT auto-align or normalize. "
        f"6. Texture: Replicate material luster and stitching from {detail_src} "
        "with pixel-level accuracy. "
        f"7. Background: Professional studio setting{bg_clause} "
        "Output: Ultra-realistic, 8K resolution, e-commerce standard."
    )

# Local save path. Set to None to skip local saving.
SAVE_PATH = r"D:\images\output\MWX2503BK71_result.jpg"

# ============================================================
# Cloudflare R2 upload (optional)
# Set R2_ENABLED = True and fill in the credentials to upload
# the result directly to your R2 bucket after generation.
# ============================================================
R2_ENABLED       = True
R2_ACCOUNT_ID    = "af51016d1487afef5637f23021b4afae"          # Cloudflare Account ID
R2_ACCESS_KEY    = "7b045796381110ff94a8d04b2c8ca5cd"    # R2 API token Access Key ID
R2_SECRET_KEY    = "3909915eed734473dcd30167da80532b1d829b973366d67055442775cf1291d6"
R2_BUCKET        = "product-assets"
# Object key base name. A timestamp (_YYYYMMDD_HHMMSS) is appended at runtime
# so each run produces a unique file and nothing gets overwritten.
R2_OBJECT_KEY    = "ai_gen/MWX2503BK71_result.jpg"  # → ai_gen/MWX2503BK71_result_20260228_153045.jpg
# Public URL prefix for the bucket (r2.dev subdomain or custom domain).
# Example: "https://pub-xxxx.r2.dev"  or  "https://cdn.yourdomain.com"
R2_PUBLIC_PREFIX = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev"

# ============================================================
# Main
# ============================================================


def main():
    if not GRSAI_API_KEY or GRSAI_API_KEY == "PASTE_YOUR_GRSAI_API_KEY_HERE":
        raise ValueError("Please paste your GrsAI API key into GRSAI_API_KEY before running.")
    if not TARGET_MODEL_URL or TARGET_MODEL_URL == "PASTE_TARGET_ASIAN_MODEL_URL_HERE":
        raise ValueError("Please set TARGET_MODEL_URL to your target Asian male model photo URL.")

    # Build url list and matching img_n prompt references dynamically.
    # Slot assignments:
    #   img_1  = target model (always)
    #   img_2  = front flat garment (always)
    #   img_3  = back flat (if provided) OR texture detail
    #   img_4  = texture detail (only when back flat is present) OR background
    #   img_5  = background (only when both back flat and background are present)
    urls = [TARGET_MODEL_URL, GARMENT_URLS["flat"]]  # img_1, img_2

    has_back = bool(GARMENT_URLS.get("back"))
    if has_back:
        urls.append(GARMENT_URLS["back"])    # img_3 = back flat
        urls.append(GARMENT_URLS["detail"])  # img_4 = texture detail
        garment_src = "img_2 (front flat) and img_3 (back flat)"
        detail_src  = "img_4"
        next_idx    = 5
    else:
        urls.append(GARMENT_URLS["detail"])  # img_3 = texture detail
        garment_src = "img_2"
        detail_src  = "img_3"
        next_idx    = 4

    if BACKGROUND_URL:
        urls.append(BACKGROUND_URL)
        bg_clause = f" similar to img_{next_idx}."
    else:
        bg_clause = "."

    print(f"DEBUG: Identity anchor (img_1): {urls[0]}")
    assert urls[0] == TARGET_MODEL_URL, "img_1 is not TARGET_MODEL_URL — check slot logic!"
    prompt = _build_prompt(garment_src, detail_src, bg_clause, mode=STYLE_MODE)

    print("=== Input images (in img_n order) ===")
    slot_labels = (
        ["img_1 (target model)", "img_2 (front flat)"]
        + (["img_3 (back flat)", "img_4 (texture detail)"] if has_back
           else ["img_3 (texture detail)"])
        + ([f"img_{next_idx} (background)"] if BACKGROUND_URL else [])
    )
    for label, url in zip(slot_labels, urls):
        print(f"  {label}: {url}")

    print("\n=== Original garment model refs (not sent to API) ===")
    for name, url in ORIGINAL_MODEL_REFS.items():
        print(f"  {name}: {url}")

    print(f"\n=== Prompt ===\n{prompt}\n")
    print("=== Submit generation task ===")
    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    result_url = client.generate_and_wait(
        urls=urls,
        prompt=prompt,
        model=MODEL,
        aspect_ratio=ASPECT_RATIO,
        image_size=IMAGE_SIZE,
        negative_prompt=NEGATIVE_PROMPT,
    )

    if not result_url:
        print("[ERROR] Image generation failed. Check logs above.")
        return

    # Download the result image once; reuse bytes for both local save and R2 upload.
    img_data: bytes | None = None
    if SAVE_PATH or R2_ENABLED:
        print(f"\nDownloading result image...")
        img_data = requests.get(result_url, timeout=60).content

    if SAVE_PATH and img_data is not None:
        os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
        with open(SAVE_PATH, "wb") as f:
            f.write(img_data)
        print(f"Saved locally: {SAVE_PATH}")

    if R2_ENABLED and img_data is not None:
        stem, ext = os.path.splitext(R2_OBJECT_KEY)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        r2_key = f"{stem}_{ts}{ext}"
        content_type = "image/png" if ext.lower() == ".png" else "image/jpeg"
        ok = upload_bytes_to_r2(
            data=img_data,
            object_key=r2_key,
            account_id=R2_ACCOUNT_ID,
            access_key_id=R2_ACCESS_KEY,
            secret_access_key=R2_SECRET_KEY,
            bucket_name=R2_BUCKET,
            content_type=content_type,
        )
        if ok:
            public_url = f"{R2_PUBLIC_PREFIX.rstrip('/')}/{r2_key}"
            print(f"R2 public URL: {public_url}")

    if not SAVE_PATH and not R2_ENABLED:
        print(f"\nResult image URL: {result_url}")


if __name__ == "__main__":
    main()
