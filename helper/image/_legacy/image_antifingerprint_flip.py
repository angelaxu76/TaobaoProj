import os
import random
import argparse
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import numpy as np

# ==== 通用配置 ====
ROTATE_RANGE = (-2, 2)         # 随机旋转角度范围
CROP_PERCENT = (0.5, 1.5)      # 随机裁剪百分比范围
BORDER_PADDING = 20            # 图像四周加白边
NOISE_OPACITY = 0.04           # 透明噪点叠加
FLIP_PROBABILITY = 0.5         # 水平翻转概率


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

        # 加白边，防止旋转后裁切
        img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255))

        # 随机旋转
        angle = random.uniform(*ROTATE_RANGE)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))

        # 随机裁剪
        crop_percent = random.uniform(*CROP_PERCENT)
        img = safe_crop(img, crop_percent)

        # 随机水平翻转
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # 亮度 & 对比度扰动
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.97, 1.03))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.97, 1.03))

        # 透明噪点
        img = add_noise_layer(img)

        # 保存
        img = img.convert("RGB")
        img.save(out_path, quality=90)
        print(f"✅ 已处理: {img_path.name}")


def batch_process_images(input_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for file in input_dir.glob("*.jpg"):
        out_file = output_dir / file.name
        edit_image(file, out_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="通用图像扰动处理脚本")
    parser.add_argument("--input", type=str, required=True, help="输入文件夹路径")
    parser.add_argument("--output", type=str, required=True, help="输出文件夹路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    batch_process_images(input_path, output_path)
