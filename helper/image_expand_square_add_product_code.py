# image_defender_like_square.py
# 供 pipeline 直接 import 调用：process_images(input_dir, output_dir, product_code, defend=True/False)

from __future__ import annotations
from pathlib import Path
import random
import re
import numpy as np
from typing import Iterable, Tuple, List
from PIL import Image, ImageEnhance, ImageOps

# ===== 固定参数（与你原脚本风格一致）=====
JPEG_QUALITY = 90
BG_RGB = (255, 255, 255)     # 方图白底
ROTATE_RANGE = (-1.2, 1.2)   # 比原先更轻，减少几何失真
CROP_PERCENT_RANGE = (0.4, 1.0)  # 0.4%~1.0% 轻裁剪
BRIGHTNESS_JITTER = 0.03     # 亮度±3%
CONTRAST_JITTER = 0.03       # 对比度±3%
NOISE_OPACITY = 0.03         # 0~1 的透明度，轻微颗粒感（不会“盖黑”）
BORDER_PADDING = 20          # 防旋转裁切的安全白边

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]

def _iter_images(input_dir: Path) -> Iterable[Path]:
    for p in sorted(input_dir.iterdir(), key=lambda x: _natural_key(x.name)):
        if p.is_file() and p.suffix.lower() in VALID_EXT and not p.name.startswith("."):
            yield p

def _to_square_canvas(im: Image.Image) -> Image.Image:
    """不缩放主体，铺成正方形（白底居中）。"""
    w, h = im.size
    side = max(w, h)
    if im.mode in ("RGBA", "LA"):
        base = Image.new("RGB", im.size, BG_RGB)
        rgba = im.convert("RGBA")
        base.paste(rgba, mask=rgba.split()[-1])
        im = base
    elif im.mode != "RGB":
        im = im.convert("RGB")
    canvas = Image.new("RGB", (side, side), BG_RGB)
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    return canvas

def _safe_crop(img: Image.Image, percent: float) -> Image.Image:
    w, h = img.size
    dx = int(w * percent / 100.0)
    dy = int(h * percent / 100.0)
    # 上限保护：不超过边长的 1/20，避免切到主体
    dx = min(dx, w // 20)
    dy = min(dy, h // 20)
    return img.crop((dx, dy, w - dx, h - dy))

def _add_noise(img: Image.Image, opacity: float) -> Image.Image:
    """叠加半透明噪点（0~1 透明度），扰乱指纹但肉眼几乎无感。"""
    w, h = img.size
    noise = np.random.randint(0, 50, (h, w, 3), dtype="uint8")
    layer = Image.fromarray(noise, "RGB").convert("RGBA")
    alpha = int(max(0.0, min(1.0, opacity)) * 255)  # ✅ 注意：这里才 *255
    layer.putalpha(alpha)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

def _defender_like(im: Image.Image) -> Image.Image:
    """按你原脚本的处理顺序：白边→旋转→镜像→轻裁→亮度/对比度→噪点。"""
    im = ImageOps.expand(im.convert("RGB"), border=BORDER_PADDING, fill=BG_RGB)
    angle = random.uniform(*ROTATE_RANGE)
    im = im.rotate(angle, expand=True, fillcolor=BG_RGB)
    cp = random.uniform(*CROP_PERCENT_RANGE)
    im = _safe_crop(im, cp)
    im = ImageEnhance.Brightness(im).enhance(random.uniform(1 - BRIGHTNESS_JITTER, 1 + BRIGHTNESS_JITTER))
    im = ImageEnhance.Contrast(im).enhance(random.uniform(1 - CONTRAST_JITTER, 1 + CONTRAST_JITTER))
    im = _add_noise(im, opacity=NOISE_OPACITY)
    return im

def _save_jpeg(im: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True, subsampling=1)

def process_images(input_dir: str | Path, output_dir: str | Path, product_code: str, defend: bool = True) -> List[Path]:
    """
    按你原有风格处理，并在保存前铺方图：
    - 输出到 <output>/<product_code>/ 下
    - 命名为 <product_code>_1.jpg, _2.jpg...
    - defend=False 时仅铺方图（不做旋转/裁剪/噪点等）
    """
    input_dir = Path(input_dir)
    out_dir = Path(output_dir) / product_code
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: List[Path] = []
    for idx, src in enumerate(_iter_images(input_dir), start=1):
        out_path = out_dir / f"{product_code}_{idx}.jpg"
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                if defend:
                    im = _defender_like(im)  # 仅做轻微扰动，不做去噪/锐化
                # 最后统一铺成正方形
                im = _to_square_canvas(im)
                _save_jpeg(im, out_path)
            outputs.append(out_path)
        except Exception as e:
            print(f"⚠ 跳过 {src.name}: {e}")
    return outputs
