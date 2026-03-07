# -*- coding: utf-8 -*-
"""
图像防指纹扰动处理。

对图片做微小随机变化（旋转、裁剪、亮度、噪点、可选翻转），
使平台图像识别无法精确匹配，降低侵权/重复检测风险。

调用方式：
    from helper.image.image_antifingerprint import batch_process_images

    # 不翻转（Barbour 商品图，保持方向）
    batch_process_images(IMAGE_IN=src, IMAGE_OUT=dst)

    # 带翻转（Ecco / Birkenstock 等）
    batch_process_images(src, dst, flip=True)
"""

import random
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
import numpy as np

# ==== 默认配置 ====
ROTATE_RANGE   = (-2, 2)       # 随机旋转角度范围
CROP_PERCENT   = (0.5, 1.5)    # 随机裁剪百分比范围
BORDER_PADDING = 20            # 图像四周加白边（防旋转后内容贴边）
NOISE_OPACITY  = 0.04          # 透明噪点叠加强度


def _add_noise_layer(img: Image.Image) -> Image.Image:
    w, h = img.size
    noise = np.random.randint(0, 50, (h, w, 3), dtype="uint8")
    noise_img = Image.fromarray(noise, "RGB").convert("RGBA")
    noise_img.putalpha(int(255 * NOISE_OPACITY))
    return Image.alpha_composite(img.convert("RGBA"), noise_img)


def _safe_crop(img: Image.Image, crop_percent: float = 1.0) -> Image.Image:
    w, h = img.size
    dx = int(w * crop_percent / 100)
    dy = int(h * crop_percent / 100)
    return img.crop((dx, dy, w - dx, h - dy))


def edit_image(img_path: Path, out_path: Path, flip: bool = False):
    """对单张图片做防指纹扰动并保存。flip=True 时加随机水平翻转。"""
    with Image.open(img_path) as img:
        img = img.convert("RGB")
        img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255))
        angle = random.uniform(*ROTATE_RANGE)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        crop_pct = random.uniform(*CROP_PERCENT)
        img = _safe_crop(img, crop_pct)
        if flip:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.97, 1.03))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.97, 1.03))
        img = _add_noise_layer(img)
        img = img.convert("RGB")
        img.save(out_path, quality=90)
        print(f"  ✅ {img_path.name}")


def batch_process_images(input_dir=None, output_dir=None, flip: bool = False,
                         IMAGE_IN=None, IMAGE_OUT=None):
    """
    批量防指纹处理，支持两种调用约定：

    新约定（ecco/birkenstock 风格）：
        batch_process_images(src_path, dst_path, flip=True)

    旧约定（barbour 风格，向后兼容）：
        batch_process_images(IMAGE_IN=src_path, IMAGE_OUT=dst_path)
    """
    in_dir  = Path(input_dir  or IMAGE_IN)
    out_dir = Path(output_dir or IMAGE_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)

    exts = {".jpg", ".jpeg", ".png", ".webp"}
    files = [p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    print(f"防指纹处理：{in_dir}，共 {len(files)} 张，flip={flip}")

    for f in files:
        out_path = out_dir / f.name
        try:
            edit_image(f, out_path, flip=flip)
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")

    print(f"完成：{len(files)} 张")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="图像防指纹扰动")
    parser.add_argument("--input",  required=True, help="输入目录")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--flip",   action="store_true", help="加随机水平翻转")
    args = parser.parse_args()
    batch_process_images(args.input, args.output, flip=args.flip)
