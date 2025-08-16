# -*- coding: utf-8 -*-
"""
Barbour 透明抠图一键合成 (多线程版本)：
1) 根据服装主色亮度自动挑选背景
2) 合成自然投影
3) “防扫描”扰动（旋转/亮度对比度抖动/轻噪点/安全裁边）
"""

import random
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageEnhance

# 画布与排版
CANVAS_SIZE = (3000, 3000)
FIT_RATIO   = (0.72, 0.88)

# 投影参数
SHADOW_OFFSET = (int(CANVAS_SIZE[0]*0.012), int(CANVAS_SIZE[1]*0.018))
SHADOW_BLUR   = 25
SHADOW_ALPHA  = 110

# 防扫描扰动
BORDER_PADDING   = 24
ROTATE_RANGE_DEG = (-1.8, 1.8)
BRIGHT_JITTER    = (0.97, 1.03)
CONTRAST_JITTER  = (0.97, 1.03)

# 噪点
NOISE_OPACITY = 0.03
NOISE_INTENS  = 28

# 亮度阈值
DARK_THR  = 105
LIGHT_THR = 175

# ============== 工具函数（不变） ==============

def list_images(directory: Path) -> List[Path]:
    return sorted([p for p in directory.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])

def ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img

def compute_subject_luminance(fg_rgba: Image.Image) -> float:
    arr = np.array(fg_rgba)
    alpha = arr[..., 3]
    mask = alpha > 10
    if not mask.any():
        return 150.0
    rgb = arr[..., :3][mask]
    y = 0.2126*rgb[:,0] + 0.7152*rgb[:,1] + 0.0722*rgb[:,2]
    return float(y.mean())

def categorize_backgrounds(bg_paths: List[Path]) -> Tuple[List[Path], List[Path], List[Path]]:
    lights, neutrals, darks = [], [], []
    for p in bg_paths:
        try:
            img = Image.open(p).convert("RGB").resize((300, 300))
            arr = np.asarray(img, dtype=np.float32)
            y = (0.2126*arr[...,0] + 0.7152*arr[...,1] + 0.0722*arr[...,2]).mean()
            if y >= 175:
                lights.append(p)
            elif y <= 110:
                darks.append(p)
            else:
                neutrals.append(p)
        except Exception:
            continue
    return lights, neutrals, darks

def choose_background(bg_paths_all: List[Path], subject_y: float) -> Path:
    lights, neutrals, darks = categorize_backgrounds(bg_paths_all)
    if subject_y <= DARK_THR:
        pool = lights or neutrals or darks
    elif subject_y >= LIGHT_THR:
        pool = darks or neutrals or lights
    else:
        pool = neutrals or lights or darks
    return random.choice(pool)

def jitter_image(img: Image.Image) -> Image.Image:
    img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255, 0))
    angle = random.uniform(*ROTATE_RANGE_DEG)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(random.uniform(*BRIGHT_JITTER))
    rgb = ImageEnhance.Contrast(rgb).enhance(random.uniform(*CONTRAST_JITTER))
    img = Image.merge("RGBA", (*rgb.split(), img.split()[-1]))
    return img

def add_drop_shadow(bg: Image.Image, fg_rgba: Image.Image, position: Tuple[int,int]) -> Image.Image:
    x, y = position
    shadow = Image.new("RGBA", fg_rgba.size, (0,0,0,0))
    alpha = fg_rgba.split()[-1]
    shadow.putalpha(alpha)
    shadow = ImageOps.expand(shadow, border=3, fill=(0,0,0,0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    r,g,b,a = shadow.split()
    a = a.point(lambda v: min(255, int(v*SHADOW_ALPHA/255)))
    shadow = Image.merge("RGBA", (Image.new("L", r.size, 0),)*3 + (a,))
    bg.alpha_composite(shadow, (x+SHADOW_OFFSET[0], y+SHADOW_OFFSET[1]))
    return bg

def fit_foreground_to_canvas(fg_rgba: Image.Image, canvas_size: Tuple[int,int]) -> Image.Image:
    ratio = random.uniform(*FIT_RATIO)
    max_len = int(max(canvas_size) * ratio)
    w, h = fg_rgba.size
    scale = max_len / max(w, h)
    new_size = (max(1, int(w*scale)), max(1, int(h*scale)))
    return fg_rgba.resize(new_size, Image.LANCZOS)

def add_final_noise(img_rgb: Image.Image) -> Image.Image:
    w, h = img_rgb.size
    noise = np.random.randint(0, NOISE_INTENS+1, (h, w, 3), dtype=np.uint8)
    noise_img = Image.fromarray(noise, "RGB").convert("RGBA")
    noise_img.putalpha(int(NOISE_OPACITY*255))
    base = img_rgb.convert("RGBA")
    out = Image.alpha_composite(base, noise_img).convert("RGB")
    return out

def resize_bg_cover(bg_img: Image.Image, canvas_size: Tuple[int,int]) -> Image.Image:
    bg = bg_img.copy().convert("RGB")
    bg_w, bg_h = bg.size
    c_w, c_h = canvas_size
    scale = max(c_w / bg_w, c_h / bg_h)
    new_size = (int(bg_w*scale), int(bg_h*scale))
    bg = bg.resize(new_size, Image.LANCZOS)
    left = (bg.width - c_w) // 2
    top  = (bg.height - c_h) // 2
    bg = bg.crop((left, top, left + c_w, top + c_h))
    return bg

# ============== 主流程 ==============

def process_one(fg_path: Path, bg_candidates: List[Path], out_dir: Path):
    fg = ensure_rgba(Image.open(fg_path))
    subj_y = compute_subject_luminance(fg)
    bg_path = choose_background(bg_candidates, subj_y)

    bg = resize_bg_cover(Image.open(bg_path), CANVAS_SIZE).convert("RGBA")
    canvas = bg.copy()

    fg_jittered = jitter_image(fg)
    fg_fitted   = fit_foreground_to_canvas(fg_jittered, CANVAS_SIZE)

    x = (CANVAS_SIZE[0] - fg_fitted.width) // 2
    y = (CANVAS_SIZE[1] - fg_fitted.height) // 2

    canvas = add_drop_shadow(canvas, fg_fitted, (x, y))
    canvas.alpha_composite(fg_fitted, (x, y))

    out_rgb = add_final_noise(canvas.convert("RGB"))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{fg_path.stem}.jpg"
    out_file = out_dir / out_name
    out_rgb.save(out_file, quality=92, subsampling=2)
    print(f"✅ 合成完成: {fg_path.name}  →  背景[{bg_path.name}]  →  {out_file}")

def image_composer(
    fg_dir: Path = Path(r"D:\TB\Products\barbour\images\透明图"),
    bg_dir: Path = Path(r"D:\TB\Products\barbour\images\backgrounds"),
    out_dir: Path = Path(r"D:\TB\Products\barbour\images\output"),
    max_workers: int = 6
):
    fg_list = [p for p in list_images(fg_dir) if p.suffix.lower() == ".png"]
    if not fg_list:
        print("⚠️ 未找到任何 PNG 透明图。")
        return
    bg_list = list_images(bg_dir)
    if not bg_list:
        print("⚠️ 未找到任何背景图。")
        return

    print(f"🔎 前景 {len(fg_list)} 张，背景 {len(bg_list)} 张，开始合成 (并发 {max_workers})…")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, fg, bg_list, out_dir): fg for fg in fg_list}
        for fut in as_completed(futures):
            fg = futures[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"❌ 处理失败：{fg.name} -> {e}")

if __name__ == "__main__":
    image_composer()
