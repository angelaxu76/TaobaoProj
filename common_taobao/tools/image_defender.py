import os
import random
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import numpy as np

INPUT_DIR = Path(r"D:\TB\Products\ECCO\document\square_images_new")
OUTPUT_DIR = Path(r"D:\TB\Products\ECCO\document\square_images_defence")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ROTATE_RANGE = (-2, 2)  # 控制旋转角度小于 ±2°
CROP_PERCENT = (0.5, 1.5)  # 控制裁剪量更小
BORDER_PADDING = 20  # 给图片加白边，避免贴边
NOISE_OPACITY = 0.04

def add_noise_layer(img: Image.Image) -> Image.Image:
    width, height = img.size
    noise = np.random.randint(0, 50, (height, width, 3), dtype='uint8')
    noise_img = Image.fromarray(noise, 'RGB').convert("RGBA")
    noise_img.putalpha(int(255 * NOISE_OPACITY))
    return Image.alpha_composite(img.convert("RGBA"), noise_img)

def safe_crop(img: Image.Image, crop_percent=1.0):
    w, h = img.size
    dx = int(w * crop_percent / 100)
    dy = int(h * crop_percent / 100)
    return img.crop((dx, dy, w - dx, h - dy))

def edit_image(img_path: Path, out_path: Path):
    with Image.open(img_path) as img:
        img = img.convert("RGB")

        # 给图像加一圈白边，避免旋转后内容贴边被裁
        img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255))

        # 旋转时启用 expand，避免裁切
        angle = random.uniform(*ROTATE_RANGE)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))

        # 裁剪安全边缘
        crop_percent = random.uniform(*CROP_PERCENT)
        img = safe_crop(img, crop_percent)

        # 轻微亮度、对比度变化
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.97, 1.03))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.97, 1.03))

        # 添加透明噪点
        img = add_noise_layer(img)

        # 保存最终结果
        img = img.convert("RGB")
        img.save(out_path, quality=90)
        print(f"✅ 已处理: {img_path.name}")

def batch_process_images():
    for file in INPUT_DIR.glob("*.jpg"):
        out_file = OUTPUT_DIR / file.name
        edit_image(file, out_file)

if __name__ == "__main__":
    batch_process_images()
