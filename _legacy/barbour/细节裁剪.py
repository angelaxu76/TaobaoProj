# -*- coding: utf-8 -*-
"""
AutoCrop Barbour Details - 适合白底模特图的细节自动裁切
依赖: pip install opencv-python pillow numpy
用法:
    INPUT_DIR  放白底原图
    OUTPUT_DIR 自动输出裁剪图
    可按需调整 ROI_PERCENT 的百分比框
    如有胸章模板(小图)，填写 BADGE_TEMPLATE_PATH 可自动微调胸章位置
"""

import cv2
import numpy as np
from pathlib import Path
from PIL import Image

# ====== 可调参数 ======
INPUT_DIR = Path(r"D:\imgs\MSP0146\input")     # 原图目录
OUTPUT_DIR = Path(r"D:\imgs\MSP0146\crops")    # 输出目录
BADGE_TEMPLATE_PATH = r"D:\imgs\badge_template.png"  # 可选：胸章小图模板（透明或白底均可），留空则不用模板匹配
OUT_EXT = ".jpg"                                 # 输出格式 .jpg/.png/.webp
QUALITY = 92

# 裁剪区域(相对衣服外接框的百分比) [x1,y1,x2,y2]，0~1
# 这些比例基于正面站立的 Barbour 国际线机拍图，可按需要微调
ROI_PERCENT = {
    "collar":   [0.30, 0.00, 0.70, 0.26],  # 领口/门襟上半部
    "badgeL":   [0.08, 0.28, 0.42, 0.48],  # 左胸(图片左侧) 徽章区域
    "placket":  [0.43, 0.18, 0.58, 0.75],  # 中央门襟/拉链区域
    "cuffR":    [0.62, 0.62, 0.98, 0.95],  # 右侧袖口(图片右侧)
    "hem":      [0.25, 0.70, 0.75, 1.00],  # 下摆
}

# 背景阈值（白底），越小越严格
WHITE_BG_THR = 245       # 像素>阈值视为白背景
MIN_AREA_RATIO = 0.15    # 目标最小占图比例(防止误检)


def read_image_cv(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    return img

def save_pil(img: Image.Image, path: Path, quality=QUALITY):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".webp":
        img.save(path, "WEBP", quality=quality, method=6)
    elif path.suffix.lower() == ".png":
        img.save(path, "PNG", optimize=True)
    else:
        img.save(path, "JPEG", quality=quality, optimize=True)

def largest_foreground_bbox(img_bgr):
    h, w = img_bgr.shape[:2]
    # 估算前景: 远离纯白
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # 距离白色的“暗度”
    inv = 255 - gray
    # 把近白像素置0，其余保留
    mask = (gray < WHITE_BG_THR).astype(np.uint8) * 255

    # 去噪/连通域
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return (0, 0, w, h)

    cnt = max(cnts, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(cnt)
    if bw * bh < MIN_AREA_RATIO * w * h:
        # 兜底：全图
        return (0, 0, w, h)
    return (x, y, bw, bh)

def percent_box_to_abs(bbox, perc):
    x, y, bw, bh = bbox
    px1, py1, px2, py2 = perc
    ax1 = int(x + bw * px1)
    ay1 = int(y + bh * py1)
    ax2 = int(x + bw * px2)
    ay2 = int(y + bh * py2)
    return (max(ax1,0), max(ay1,0), ax2, ay2)

def template_refine_badge(crop_bgr, template_path):
    """ 在 badge 近似区域内用模板匹配微调裁切（可选） """
    try:
        tpl = read_image_cv(template_path)
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        img_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, maxval, _, maxloc = cv2.minMaxLoc(res)
        th, tw = tpl_gray.shape[:2]
        x1, y1 = maxloc
        x2, y2 = x1 + tw, y1 + th
        pad = int(0.25 * max(th, tw))
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(crop_bgr.shape[1], x2 + pad), min(crop_bgr.shape[0], y2 + pad)
        return crop_bgr[y1:y2, x1:x2], maxval
    except Exception:
        return crop_bgr, 0.0

def crop_and_save(img_bgr, box, out_path):
    x1, y1, x2, y2 = box
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img_bgr.shape[1], x2), min(img_bgr.shape[0], y2)
    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return
    pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    save_pil(pil, out_path)

def process_one(img_path: Path):
    img = read_image_cv(str(img_path))
    if img is None:
        return
    H, W = img.shape[:2]
    bbox = largest_foreground_bbox(img)  # (x, y, w, h)

    base = img_path.stem
    outdir = OUTPUT_DIR / base
    outdir.mkdir(parents=True, exist_ok=True)

    # 常规部位
    for key, perc in ROI_PERCENT.items():
        ax1, ay1, ax2, ay2 = percent_box_to_abs(bbox, perc)
        out_path = outdir / f"{base}_{key}{OUT_EXT}"
        crop_and_save(img, (ax1, ay1, ax2, ay2), out_path)

    # 胸章模板微调（可选）
    if BADGE_TEMPLATE_PATH:
        # 先取 badgeL 的裁片，再在内部匹配模板细化
        bx1, by1, bx2, by2 = percent_box_to_abs(bbox, ROI_PERCENT["badgeL"])
        badge_crop = img[by1:by2, bx1:bx2].copy()
        refined, score = template_refine_badge(badge_crop, BADGE_TEMPLATE_PATH)
        if refined.size:
            pil = Image.fromarray(cv2.cvtColor(refined, cv2.COLOR_BGR2RGB))
            save_pil(pil, outdir / f"{base}_badge_refined{OUT_EXT}")

def main():
    imgs = sorted([p for p in INPUT_DIR.glob("*.*") if p.suffix.lower() in {".jpg",".jpeg",".png",".webp"}])
    for p in imgs:
        process_one(p)
    print(f"✅ Done. Crops in: {OUTPUT_DIR}")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
