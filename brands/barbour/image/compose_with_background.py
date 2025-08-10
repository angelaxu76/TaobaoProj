# -*- coding: utf-8 -*-
"""
一键合成：透明PNG(PS抠好图) → 随机地毯/木地板背景 → 阴影 → 轻微扰动 → 批量JPG
依赖：pip install pillow
"""

import random
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np

# ============== 参数区（按需修改） ==============
FG_DIR   = Path(r"D:/imgs/fg_png")        # 透明PNG输入目录（Photoshop抠好图）
BG_DIR   = Path(r"D:/imgs/backgrounds")   # 背景目录（地毯/木地板，建议≥3000px）
OUT_DIR  = Path(r"D:/imgs/output")        # 输出目录
OUT_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_SIZE = (3000, 3000)   # 成品尺寸
FIT_RATIO   = 0.88           # 前景占画布最长边比例
BG_MODE = "crop"            # 等比放大背景再裁成正方形

# 投影（让衣服“贴地”更真实）
SHADOW = dict(offset=(0, 35), blur=45, opacity=110)

# 统一色调（微暖；不需要就设 None）
COLOR_TONE = 1.02            # 0.95~1.05；None=关闭

# 轻微扰动（降低指纹，视觉不变形）
RAND_BRIGHTNESS = (0.98, 1.02)
RAND_CONTRAST   = (0.98, 1.02)
ROTATE_RANGE    = (-2.0, 2.0)   # 最终成品整体轻微旋转（不翻转，避免logo反）
NOISE_OPACITY   = 0.02          # 0~1，透明噪点强度
BG_MODE         = "crop"        # "crop" | "fit" 背景适配填充方式
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
    # 轻微增暖：红更亮、蓝更暗一点点
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

def compose_one(fg_path: Path, bg_paths, out_dir: Path):
    # 读取抠好图（透明PNG）
    fg = Image.open(fg_path).convert("RGBA")
    fg = trim_transparent(fg, pad=6)

    # 1) 先缩放到画布并加阴影（保持透明背景）
    layer = fit_on_canvas(fg, CANVAS_SIZE, FIT_RATIO)
    layer = add_soft_shadow(layer, **SHADOW)

    # 2) 只旋转“前景层”，用透明填充，避免黑边
    angle = random.uniform(*ROTATE_RANGE)
    if abs(angle) > 1e-3:
        layer = layer.rotate(
            angle,
            expand=True,
            resample=Image.BICUBIC,
            fillcolor=(0, 0, 0, 0)   # 透明补边
        )
        # 旋转后再裁回目标画布并居中
        layer = ImageOps.fit(layer, CANVAS_SIZE, method=Image.LANCZOS, centering=(0.5, 0.5))

    # 3) 准备背景（不要旋转背景，避免纹理透视变形）
    bg_path = random.choice(bg_paths)
    bg = load_bg(bg_path, CANVAS_SIZE).convert("RGB")
    if COLOR_TONE:
        bg = color_tone(bg, COLOR_TONE)

    # 4) 合成 + 轻微亮度/对比度扰动 + 噪点
    comp = bg.convert("RGBA")
    comp.alpha_composite(layer, (0, 0))
    comp = comp.convert("RGB")
    comp = ImageEnhance.Brightness(comp).enhance(random.uniform(*RAND_BRIGHTNESS))
    comp = ImageEnhance.Contrast(comp).enhance(random.uniform(*RAND_CONTRAST))
    comp = add_noise(comp, NOISE_OPACITY)

    out_path = out_dir / (fg_path.stem + ".jpg")
    comp.save(out_path, quality=92, subsampling=2)
    print(f"✔ {fg_path.name} -> {out_path.name}")


def main():
    if SEED is not None:
        random.seed(SEED)

    fg_list = [p for p in list_images(FG_DIR) if p.suffix.lower()==".png"]
    if not fg_list:
        print("⚠️ 前景目录无透明PNG（请放入PS抠好的PNG）"); return
    bg_list = list_images(BG_DIR)
    if not bg_list:
        print("⚠️ 背景目录为空"); return

    for p in fg_list:
        compose_one(p, bg_list, OUT_DIR)

if __name__ == "__main__":
    main()
