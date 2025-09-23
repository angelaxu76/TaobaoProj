# -*- coding: utf-8 -*-
"""
cut_square_white_watermark.py
批量处理图片：
1) 自动裁掉透明边或白色空边
2) 白底正方形居中
3) 可选自动抠图（rembg）
4) 加水印
5) 导出高质量 JPG
"""

import os
import io
import time
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops

# ================== 可配置参数 ==================
INPUT_DIR  = r"D:\TB\Products\images_input"
OUTPUT_DIR = r"D:\TB\Products\images_output"

OUTPUT_JPEG_QUALITY = 95
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 输出统一尺寸 (像素)，设 None 则不缩放
TARGET_SIZE = 1200

# 白底颜色
CANVAS_COLOR = (255, 255, 255)

# 自动抠图设置
AUTO_CUTOUT = True   # 是否启用 rembg
MODEL_NAME = "u2net" # 可选：u2net / u2netp / u2net_human_seg 等

# 水印设置
DIAGONAL_TEXT_ENABLE = True
DIAGONAL_TEXT = "英国哈梅尔百货"
DIAGONAL_ALPHA = 30
DIAGONAL_FONT_SIZE_RATIO = 0.02
DIAGONAL_STEP_RATIO = 0.50
DIAGONAL_ANGLE_DEG = -30

LOCAL_LOGO_ENABLE = True
LOCAL_LOGO_TEXT = "英国哈梅尔百货"
LOCAL_FONT_SIZE_RATIO = 0.04
LOCAL_MARGIN_RATIO = 0.03
LOCAL_BG_ALPHA = 96
LOCAL_TEXT_ALPHA = 40

FONT_PATH = None  # 如 r"C:\Windows\Fonts\msyh.ttc"

# ================== 工具函数 ==================
def _get_font(px: int):
    try:
        if FONT_PATH:
            return ImageFont.truetype(FONT_PATH, px)
        for name in ["msyh.ttc", "simhei.ttf", "arial.ttf"]:
            try:
                return ImageFont.truetype(name, px)
            except Exception:
                pass
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("LA", "RGBA", "PA") or ("transparency" in img.info)

def _autocrop_by_alpha(img: Image.Image, thr: int = 5) -> Image.Image:
    if not _has_alpha(img):
        return img
    rgba = img.convert("RGBA")
    alpha = np.array(rgba.split()[-1])
    mask = alpha > thr
    if not mask.any():
        return rgba
    ys, xs = np.where(mask)
    y1, y2 = ys.min(), ys.max() + 1
    x1, x2 = xs.min(), xs.max() + 1
    return rgba.crop((x1, y1, x2, y2))

def _autocrop_white_border(img: Image.Image, tol: int = 8) -> Image.Image:
    if _has_alpha(img):
        return img
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, CANVAS_COLOR)
    diff = ImageChops.difference(rgb, bg)
    diff = ImageChops.add(diff, diff, 2.0, -tol)
    bbox = diff.getbbox()
    return rgb.crop(bbox) if bbox else rgb

def _pad_to_square_white(img: Image.Image, target_size: int = None) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    side = max(w, h)
    if target_size is not None:
        scale = target_size / float(side)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
        side = target_size
        w, h = img.size
    canvas = Image.new("RGB", (side, side), CANVAS_COLOR)
    x = (side - w) // 2
    y = (side - h) // 2
    canvas.paste(img, (x, y))
    return canvas

# ================== 自动抠图 (rembg) ==================
from rembg import remove, new_session

_SESSION = None
def get_session():
    global _SESSION
    if _SESSION is None and AUTO_CUTOUT:
        print("⏳ 正在加载抠图模型（首次会下载 ~170MB，耐心等待一次即可）...")
        _SESSION = new_session(MODEL_NAME)
        print("✅ 模型就绪")
    return _SESSION

def ensure_cutout(img: Image.Image) -> Image.Image:
    if not AUTO_CUTOUT:
        return img
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if "A" in img.getbands():
        amin, amax = img.split()[-1].getextrema()
        if amin < 255 and amax > 0:
            return img
    sess = get_session()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    cut = remove(buf.getvalue(), session=sess)
    return Image.open(io.BytesIO(cut)).convert("RGBA")

# ================== 水印 ==================
def add_diagonal_text_watermark(img: Image.Image) -> Image.Image:
    if not DIAGONAL_TEXT_ENABLE or not DIAGONAL_TEXT:
        return img
    img = img.convert("RGBA")
    w, h = img.size
    font = _get_font(max(16, int(w * DIAGONAL_FONT_SIZE_RATIO)))
    pad = int(max(w, h) * 0.25)
    tile_w, tile_h = w + pad * 2, h + pad * 2
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tile)
    text_w = tdraw.textlength(DIAGONAL_TEXT, font=font)
    step = max(10, int(w * DIAGONAL_STEP_RATIO))
    for y in range(0, tile_h, step):
        x = -tile_w
        while x < tile_w * 2:
            tdraw.text((x, y), DIAGONAL_TEXT, font=font, fill=(0, 0, 0, DIAGONAL_ALPHA))
            x += int(text_w * 1.5)
    tile = tile.rotate(DIAGONAL_ANGLE_DEG, expand=1, resample=Image.BICUBIC)
    tw, th = tile.size
    cx, cy = tw // 2, th // 2
    left, top = cx - w // 2, cy - h // 2
    tile_cropped = tile.crop((left, top, left + w, top + h))
    return Image.alpha_composite(img, tile_cropped).convert("RGB")

def add_local_logo(img: Image.Image, text: str = None) -> Image.Image:
    if not LOCAL_LOGO_ENABLE:
        return img
    text = text or LOCAL_LOGO_TEXT or ""
    if not text:
        return img
    img = img.convert("RGBA")
    w, h = img.size
    font = _get_font(max(14, int(w * LOCAL_FONT_SIZE_RATIO)))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = draw.textlength(text, font=font), font.size
    margin = int(w * LOCAL_MARGIN_RATIO)
    x, y = w - tw - margin, h - th - margin
    draw.rectangle([x - margin // 2, y - margin // 4, x + tw + margin // 2, y + th + margin // 4],
                   fill=(255, 255, 255, LOCAL_BG_ALPHA))
    draw.text((x, y), text, font=font, fill=(0, 0, 0, LOCAL_TEXT_ALPHA))
    return Image.alpha_composite(img, overlay).convert("RGB")

# ================== 主流程 ==================
def process_one(path: Path, out_dir: Path):
    try:
        img = Image.open(str(path))
        img = ensure_cutout(img)
        if _has_alpha(img):
            img = _autocrop_by_alpha(img, thr=5)
        else:
            img = _autocrop_white_border(img, tol=8)
        img = _pad_to_square_white(img, target_size=TARGET_SIZE)
        img = add_diagonal_text_watermark(img)
        img = add_local_logo(img, LOCAL_LOGO_TEXT)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = path.stem + ".jpg"
        img.save(str(out_dir / out_name),
                 quality=OUTPUT_JPEG_QUALITY, subsampling=0, optimize=True)
        print(f"✅ {path.name} -> {out_name}")
    except Exception as e:
        print(f"❌ 处理失败：{path.name}，错误：{e}")

def batch_process(input_dir: str, output_dir: str):
    in_dir = Path(input_dir); out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 正在扫描目录: {in_dir.resolve()}")
    groups = {}
    for p in in_dir.iterdir():
        if p.is_file():
            print(f"  检查文件: {p.name}")
            if p.suffix.lower() in SUPPORTED_EXTS:
                print(f"    ✅ 命中文件: {p.name}")
                groups.setdefault(p.stem.lower(), []).append(p)
            else:
                print(f"    ⏭️ 跳过（后缀不支持）: {p.suffix}")

    # 按同名优先 PNG
    files = []
    for stem, lst in groups.items():
        lst.sort(key=lambda x: (x.suffix.lower() != ".png", x.name))
        files.append(lst[0])

    total = len(files)
    print(f"📊 共找到 {total} 张待处理图片")
    if total == 0:
        print("⚠️ 未发现可处理的图片。请确认目录和文件后缀。")
        return

    t0 = time.time()
    for i, p in enumerate(files, 1):
        print(f"[{i}/{total}] ▶ 开始处理 {p.name}")
        process_one(p, out_dir)
    print(f"🎉 全部完成！耗时 {time.time()-t0:.1f}s")

if __name__ == "__main__":
    batch_process(INPUT_DIR, OUTPUT_DIR)
