# -*- coding: utf-8 -*-
"""
PS透明PNG → 主色识别(仅衣服像素) → 按颜色选背景 → 阴影 → 轻微扰动 → 批量JPG
依赖：pip install pillow opencv-python numpy
"""

import random
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np
import cv2

# ============== 参数区（按需修改） ==============
FG_DIR   = Path(r"D:/imgs/fg_png")        # 仅处理 .png（PS已抠好，含透明）
BG_DIR   = Path(r"D:/imgs/backgrounds")   # 背景目录：四张命名背景即可
OUT_DIR  = Path(r"D:/imgs/output")        # 输出目录
OUT_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_SIZE = (3000, 3000)   # 成品尺寸
FIT_RATIO   = 0.88           # 前景占画布最长边比例

# 背景适配方式
BG_MODE         = "crop"     # "crop" | "fit"

# 投影（让衣服“贴地”更真实）
SHADOW = dict(offset=(0, 35), blur=45, opacity=110)

# 统一色调（微暖；不需要就设 None）
COLOR_TONE = 1.02            # 0.95~1.05；None=关闭

# 轻微扰动（降低指纹，视觉不变形）
RAND_BRIGHTNESS = (0.98, 1.02)
RAND_CONTRAST   = (0.98, 1.02)
ROTATE_RANGE    = (-2.0, 2.0)   # 最终成品整体轻微旋转（不翻转，避免logo反）
NOISE_OPACITY   = 0.02          # 0~1，透明噪点强度

SEED            = None          # 固定随机可设整数；None 表示每次都随机
# ==============================================


def list_images(folder: Path):
    return [p for p in folder.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")]

def load_bg(path: Path, size):
    bg = Image.open(path).convert("RGB")
    if BG_MODE == "fit":
        return ImageOps.fit(bg, size, method=Image.LANCZOS, centering=(0.5, 0.5))
    return ImageOps.fit(bg, size, method=Image.LANCZOS)

def trim_transparent(png: Image.Image, pad=6):
    if png.mode != "RGBA":
        png = png.convert("RGBA")
    bbox = png.getbbox()
    if bbox:
        l, t, r, b = bbox
        l = max(0, l - pad); t = max(0, t - pad)
        r = min(png.width,  r + pad); b = min(png.height, b + pad)
        return png.crop((l, t, r, b))
    return png

def fit_on_canvas(fg: Image.Image, canvas_size, ratio):
    if fg.mode != "RGBA":
        fg = fg.convert("RGBA")
    w, h = fg.size
    scale = min(canvas_size) * ratio / max(w, h)
    new = fg.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    canvas = Image.new("RGBA", canvas_size, (0,0,0,0))
    cx = (canvas_size[0]-new.size[0])//2
    cy = (canvas_size[1]-new.size[1])//2
    canvas.alpha_composite(new, (cx, cy))
    return canvas

def add_soft_shadow(layer: Image.Image, offset=(0,30), blur=45, opacity=110):
    if layer.mode != "RGBA": layer = layer.convert("RGBA")
    alpha = layer.split()[-1]
    shadow = Image.new("RGBA", layer.size, (0,0,0,0))
    blurred = alpha.filter(ImageFilter.GaussianBlur(blur))
    tint = Image.new("RGBA", layer.size, (0,0,0,opacity))
    shadow.paste(tint, (0,0), blurred)
    out = Image.new("RGBA", layer.size, (0,0,0,0))
    out.alpha_composite(shadow, offset)
    out.alpha_composite(layer, (0,0))
    return out

def color_tone(img: Image.Image, factor=1.0):
    if factor is None or abs(factor-1.0) < 1e-3:
        return img
    img = img.convert("RGB")
    r,g,b = img.split()
    r = r.point(lambda x: min(255, int(x*factor)))
    b = b.point(lambda x: max(0, int(x/factor)))
    return Image.merge("RGB", (r,g,b))

def add_noise(img: Image.Image, opacity=0.02):
    if opacity <= 0: return img
    w,h = img.size
    noise = np.random.randint(0, 50, (h, w, 3), dtype="uint8")
    noise_img = Image.fromarray(noise, "RGB").convert("RGBA")
    noise_img.putalpha(int(255*opacity))
    return Image.alpha_composite(img.convert("RGBA"), noise_img).convert("RGB")

# ---------- 主色识别（忽略透明像素） ----------
def dominant_rgb_from_rgba(pil_rgba: Image.Image, k=3):
    arr = np.array(pil_rgba)
    mask = arr[:, :, 3] > 10  # 仅非透明
    pixels = arr[:, :, :3][mask]
    if pixels.size == 0:
        return (128,128,128)
    if pixels.shape[0] > 200000:
        idx = np.random.choice(pixels.shape[0], 200000, replace=False)
        pixels = pixels[idx]
    Z = np.float32(pixels)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(Z, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    dom = centers[np.bincount(labels.flatten()).argmax()].astype(np.uint8)
    return tuple(int(x) for x in dom)

def rgb_to_hsv_deg(rgb):
    bgr = np.uint8([[list(rgb[::-1])]])
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0,0]
    H = float(hsv[0]) * 2.0
    S = float(hsv[1]) / 255.0
    V = float(hsv[2]) / 255.0
    return H, S, V

def classify_color(h_deg, s, v):
    tone = "mid"
    if v < 0.38: tone = "dark"
    elif v > 0.72: tone = "light"
    hue = "neutral"
    if s >= 0.18:
        if (0 <= h_deg <= 50) or (330 <= h_deg <= 360): hue = "warm"
        elif 180 <= h_deg <= 260: hue = "cool"
    return {"tone": tone, "hue": hue}

# ---------- 背景映射 & 选择 ----------
def build_bg_dict():
    normal = lambda s: s.lower().replace(" ", "").replace("_", "")
    targets = {
        "herringboneoakwood": "HerringboneOakWood",
        "naturaloakwood": "NaturalOakWood",
        "neutralbeigewoolcarpet": "NeutralBeigeWoolCarpet",
        "warmbeigewoolcarpet": "WarmBeigeWoolCarpet",
    }
    bg_files = {}
    for p in BG_DIR.iterdir():
        if not p.is_file() or p.suffix.lower() not in {".jpg",".jpeg",".png"}:
            continue
        key = normal(p.stem)
        for k, std in targets.items():
            if k in key:
                bg_files[std] = p
                break
    return bg_files

def choose_bg_by_color(bg_files: dict, h_deg, s, v):
    fallback = [bg_files.get(k) for k in
                ["NaturalOakWood","NeutralBeigeWoolCarpet","HerringboneOakWood","WarmBeigeWoolCarpet"]]
    fallback = [p for p in fallback if p is not None]

    tone_hue = classify_color(h_deg, s, v)
    tone, hue = tone_hue["tone"], tone_hue["hue"]

    if tone == "light":
        return bg_files.get("HerringboneOakWood") or fallback[0]
    if tone == "dark":
        return bg_files.get("NaturalOakWood") or bg_files.get("NeutralBeigeWoolCarpet") or fallback[0]
    if hue == "warm":
        return bg_files.get("NeutralBeigeWoolCarpet") or bg_files.get("NaturalOakWood") or fallback[0]
    if hue == "cool":
        return bg_files.get("WarmBeigeWoolCarpet") or bg_files.get("NaturalOakWood") or fallback[0]
    return fallback[0] if fallback else None

# ---------- 合成 ----------
def compose_one(fg_path: Path, bg_path: Path, out_dir: Path):
    fg = Image.open(fg_path).convert("RGBA")
    fg = trim_transparent(fg, pad=6)

    layer = fit_on_canvas(fg, CANVAS_SIZE, FIT_RATIO)
    layer = add_soft_shadow(layer, **SHADOW)

    angle = random.uniform(*ROTATE_RANGE)
    if abs(angle) > 1e-3:
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0,0,0,0))
        layer = ImageOps.fit(layer, CANVAS_SIZE, method=Image.LANCZOS, centering=(0.5, 0.5))

    bg = load_bg(bg_path, CANVAS_SIZE).convert("RGB")
    if COLOR_TONE:
        bg = color_tone(bg, COLOR_TONE)

    comp = bg.convert("RGBA")
    comp.alpha_composite(layer, (0, 0))
    comp = comp.convert("RGB")
    comp = ImageEnhance.Brightness(comp).enhance(random.uniform(*RAND_BRIGHTNESS))
    comp = ImageEnhance.Contrast(comp).enhance(random.uniform(*RAND_CONTRAST))
    comp = add_noise(comp, NOISE_OPACITY)

    out_path = out_dir / f"{fg_path.stem}_{bg_path.stem}.jpg"
    comp.save(out_path, quality=92, subsampling=2)
    print(f"✔ {fg_path.name} + {bg_path.stem} -> {out_path.name}")

def main():
    if SEED is not None:
        random.seed(SEED)

    # 读背景并建立映射
    bg_files = build_bg_dict()
    all_bgs = list_images(BG_DIR)
    if not all_bgs:
        print("⚠️ 背景目录为空"); return

    # 只处理 PNG（PS 抠好）
    fg_list = [p for p in list_images(FG_DIR) if p.suffix.lower()==".png"]
    if not fg_list:
        print("⚠️ 前景目录无透明PNG（请放入PS抠好的PNG）"); return

    for p in fg_list:
        # 计算主色并选背景（若映射不全则回退随机）
        dom_rgb = dominant_rgb_from_rgba(Image.open(p).convert("RGBA"), k=3)
        h, s, v = rgb_to_hsv_deg(dom_rgb)
        bg_path = choose_bg_by_color(bg_files, h, s, v) if bg_files else None
        if bg_path is None:
            bg_path = random.choice(all_bgs)

        compose_one(p, bg_path, OUT_DIR)

if __name__ == "__main__":
    main()
