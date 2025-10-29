# -*- coding: utf-8 -*-
"""
自动抠图 + 批量背景合成（镜像目录）
- 输入：fg_jpg 下的 JPG/JPEG（也兼容 PNG）
- 自动抠图：OpenCV GrabCut，边缘羽化，生成透明前景
- 背景：backgrounds（随机/全量）
- 输出：output，镜像原商品目录结构
依赖：pip install opencv-python pillow numpy
"""

import random
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np
import cv2

# ============== 参数区（按需修改） ==============
FG_ROOT  = Path(r"D:/imgs/fg_jpg")       # 前景根目录（商品/图片.jpg）
BG_DIR   = Path(r"D:/imgs/backgrounds")  # 背景目录
OUT_ROOT = Path(r"D:/imgs/output")       # 输出根目录（镜像结构）
OUT_ROOT.mkdir(parents=True, exist_ok=True)

CANVAS_SIZE = (3000, 3000)   # 成品尺寸
FIT_RATIO   = 0.88           # 前景占画布最长边比例

# 背景策略："random_one"（每张前景随机若干张背景） | "all"（每张配所有背景）
BACKGROUND_POLICY = "random_one"
RANDOM_BG_COUNT = 1

# 投影
SHADOW = dict(offset=(0, 35), blur=45, opacity=110)

# 统一色调
COLOR_TONE = 1.02            # None 关闭

# 轻微扰动
RAND_BRIGHTNESS = (0.98, 1.02)
RAND_CONTRAST   = (0.98, 1.02)
ROTATE_RANGE    = (-2.0, 2.0)
NOISE_OPACITY   = 0.02

BG_MODE = "crop"             # "crop" | "fit"
APPEND_BG_NAME = True        # 文件名带上背景名
SEED = None                  # 复现实验设为整数
# ==============================================


def list_images(folder: Path):
    exts = {".png", ".jpg", ".jpeg"}
    return [p for p in folder.iterdir() if p.suffix.lower() in exts and p.is_file()]

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

# -------- 自动抠图（JPG → 透明 PNG） --------
def grabcut_cutout(jpg_path: Path) -> Image.Image:
    """
    适合：背景较干净/单色/光线均匀的平铺图（白底、浅灰底等）
    流程：
      1) 估计主体矩形 → GrabCut
      2) 形态学清理小洞
      3) 边缘羽化，减少毛边
    """
    img_bgr = cv2.imread(str(jpg_path), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise RuntimeError(f"无法读取图片：{jpg_path}")
    h, w = img_bgr.shape[:2]

    # 初步前景区域估计（去掉边缘10%作为背景，剩余作为可能的前景）
    pad = int(min(w, h) * 0.1)
    rect = (pad, pad, w - 2*pad, h - 2*pad)

    mask = np.zeros((h, w), np.uint8)
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)

    cv2.grabCut(img_bgr, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
    # 可能/确定前景
    mask2 = np.where((mask==cv2.GC_FGD) | (mask==cv2.GC_PR_FGD), 255, 0).astype('uint8')

    # 清理小噪点 + 填洞
    kernel = np.ones((5,5), np.uint8)
    mask2 = cv2.morphologyEx(mask2, cv2.MORPH_OPEN, kernel, iterations=1)
    mask2 = cv2.morphologyEx(mask2, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 羽化边缘
    feather = max(3, int(min(w, h) * 0.004))
    alpha = cv2.GaussianBlur(mask2, (0,0), feather)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    # 合成 RGBA
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack([img_rgb, alpha])
    pil_rgba = Image.fromarray(rgba, 'RGBA')

    # 裁掉多余透明边
    pil_rgba = trim_transparent(pil_rgba, pad=4)
    return pil_rgba

def read_foreground(path: Path) -> Image.Image:
    # PNG 直接用；JPG/JPEG 自动抠图
    if path.suffix.lower() == ".png":
        return Image.open(path).convert("RGBA")
    return grabcut_cutout(path)

# ---------------------------------------------

def compose_once(fg_img: Image.Image, bg_path: Path) -> Image.Image:
    fg = trim_transparent(fg_img, pad=6)
    layer = fit_on_canvas(fg, CANVAS_SIZE, FIT_RATIO)
    layer = add_soft_shadow(layer, **SHADOW)

    # 只旋转前景层
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
    return comp

def save_comp(img: Image.Image, out_dir: Path, fg_path: Path, bg_path: Path, idx: int | None):
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = fg_path.stem
    if APPEND_BG_NAME:
        suffix = f"_{bg_path.stem}"
    else:
        suffix = "" if idx is None else f"_{idx}"
    out_path = out_dir / f"{stem}{suffix}.jpg"
    img.save(out_path, quality=92, subsampling=2)
    print(f"✔ {fg_path}  +  {bg_path.name}  ->  {out_path.relative_to(OUT_ROOT)}")

def main():
    if SEED is not None:
        random.seed(SEED)

    bg_list = list_images(BG_DIR)
    if not bg_list:
        print("⚠️ 背景目录为空"); return

    # 递归遍历 JPG/PNG
    for fg_path in FG_ROOT.rglob("*"):
        if not fg_path.is_file():
            continue
        if fg_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue

        # 输出镜像目录
        rel_parent = fg_path.parent.relative_to(FG_ROOT)
        out_dir = OUT_ROOT / rel_parent

        try:
            fg_img = read_foreground(fg_path)
        except Exception as e:
            print(f"✖ 抠图失败：{fg_path} | {e}")
            continue

        if BACKGROUND_POLICY == "all":
            for bg in bg_list:
                comp = compose_once(fg_img, bg)
                save_comp(comp, out_dir, fg_path, bg, idx=None)
        else:
            k = max(1, min(RANDOM_BG_COUNT, len(bg_list)))
            chosen = random.sample(bg_list, k)
            for i, bg in enumerate(chosen, start=1):
                comp = compose_once(fg_img, bg)
                save_comp(comp, out_dir, fg_path, bg, idx=i)

if __name__ == "__main__":
    main()
