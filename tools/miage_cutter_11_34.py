# -*- coding: utf-8 -*-
"""
批量将模特图裁剪为 3:4（竖版），以“人物中心”为基准左右裁切（OpenCV 人脸检测版）。
规则：
- 目标比例固定为 3:4（width:height = 3:4）
- 尽量保持原图高度，水平裁掉两侧以达到 3:4
- 若以人物中心居中后超出一侧边界，则不裁该侧，只裁另一侧（自动贴边）
- 人物中心检测优先：人脸中心（OpenCV Haar cascade）-> 图片几何中心
"""

from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageOps
import cv2
import numpy as np

# ========== 配置 ==========
INPUT_DIR  = Path(r"D:\TEMP1\imagewater")
OUTPUT_DIR = Path(r"D:\TEMP1\43image")
RECURSIVE  = True
OVERWRITE  = True
SAVE_QUALITY = 95

# Haar cascade 模型文件（OpenCV 自带）
CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def _fix_exif_orientation(pil_img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(pil_img)

def _pil_to_cv(img: Image.Image):
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def detect_person_center_xy(pil_img: Image.Image) -> Optional[Tuple[float, float]]:
    """检测人脸中心坐标，找不到返回 None"""
    img = _pil_to_cv(pil_img)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

    if len(faces) > 0:
        # 取面积最大的人脸
        best = max(faces, key=lambda f: f[2] * f[3])
        x, y, fw, fh = best
        cx = x + fw / 2
        cy = y + fh / 2
        return (cx, cy)
    return None

def compute_3x4_crop_box(img_w: int, img_h: int, center_x: float) -> Tuple[int, int, int, int]:
    target_w = int(round(img_h * 3 / 4))
    if img_w <= target_w:
        target_h = int(round(img_w * 4 / 3))
        if target_h > img_h:
            target_h = img_h
        top = max(0, (img_h - target_h) // 2)
        bottom = top + target_h
        left = 0
        right = img_w
        return left, top, right, bottom

    half = target_w / 2.0
    left = int(round(center_x - half))
    right = left + target_w

    if left < 0:
        left = 0
        right = target_w
    if right > img_w:
        right = img_w
        left = img_w - target_w

    top = 0
    bottom = img_h
    return left, top, right, bottom

def process_image(in_path: Path, out_path: Path):
    try:
        with Image.open(in_path) as im:
            im = _fix_exif_orientation(im).convert("RGB")
            w, h = im.size

            center = detect_person_center_xy(im)
            if center is None:
                center_x = w / 2.0
            else:
                center_x, _ = center

            l, t, r, b = compute_3x4_crop_box(w, h, center_x)
            im_c = im.crop((l, t, r, b))

            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.suffix.lower() in [".jpg", ".jpeg"]:
                im_c.save(out_path, quality=SAVE_QUALITY, subsampling=1)
            else:
                im_c.save(out_path)

        print(f"✅ {in_path.name} -> {out_path.name} center_x={center_x:.1f} box=({l},{t},{r},{b})")
    except Exception as e:
        print(f"❌ {in_path}: {e}")

def valid_image(p: Path) -> bool:
    return p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"]

def main():
    files = []
    if RECURSIVE:
        files = [p for p in INPUT_DIR.rglob("*") if p.is_file() and valid_image(p)]
    else:
        files = [p for p in INPUT_DIR.iterdir() if p.is_file() and valid_image(p)]

    if not files:
        print("（没有找到待处理图片）")
        return

    print(f"共计 {len(files)} 张图片，开始处理...")
    for p in files:
        rel = p.relative_to(INPUT_DIR)
        out = (OUTPUT_DIR / rel).with_suffix(p.suffix)
        if (not OVERWRITE) and out.exists():
            print(f"跳过（已存在）：{out}")
            continue
        process_image(p, out)

if __name__ == "__main__":
    main()
