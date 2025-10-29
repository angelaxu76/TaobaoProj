import random
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
import numpy as np
from config import CAMPER

# === 输入输出路径配置 ===
INPUT_DIR = Path(CAMPER["IMAGE_DOWNLOAD"])
OUTPUT_DIR = Path(CAMPER["IMAGE_PROCESS"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 图像处理参数 ===
ROTATE_RANGE = (-2.5, 2.5)        # 旋转角度范围（度）
CROP_PERCENT = (0.4, 1.2)         # 随机裁掉四周百分比（0.4%~1.2%）
BORDER_PADDING = 20               # 旋转前加白边（像素）
NOISE_OPACITY = 0.04              # 噪点不透明度 0~1

EXTS = (".jpg", ".jpeg", ".png")

def add_noise_layer(img: Image.Image) -> Image.Image:
    """添加透明噪点图层，扰乱图像指纹"""
    w, h = img.size
    noise = np.random.randint(0, 50, (h, w, 3), dtype="uint8")
    noise_img = Image.fromarray(noise, "RGB").convert("RGBA")
    noise_img.putalpha(int(255 * NOISE_OPACITY))
    return Image.alpha_composite(img.convert("RGBA"), noise_img)

def safe_crop(img: Image.Image, crop_percent: float) -> Image.Image:
    """安全裁剪四周：crop_percent 为百分比"""
    w, h = img.size
    crop_percent = max(0.0, min(5.0, float(crop_percent)))
    dx = int(w * crop_percent / 100.0)
    dy = int(h * crop_percent / 100.0)
    left = min(dx, w // 4)
    top = min(dy, h // 4)
    right = w - left
    bottom = h - top
    if right - left < 10 or bottom - top < 10:
        return img
    return img.crop((left, top, right, bottom))

def edit_image(img_path: Path, out_path: Path):
    with Image.open(img_path) as img:
        img = img.convert("RGB")

        # 1) 添加白边
        img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255))

        # 2) 随机旋转
        angle = random.uniform(*ROTATE_RANGE)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))

        # ❌ 不做水平翻转（避免 logo 反向）

        # 3) 轻微随机裁剪
        crop_percent = random.uniform(*CROP_PERCENT)
        img = safe_crop(img, crop_percent)

        # 4) 亮度 & 对比度微调
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.97, 1.03))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.97, 1.03))

        # 5) 添加噪点扰动
        img = add_noise_layer(img)

        # 6) 保存
        img = img.convert("RGB")
        img.save(out_path, quality=90, subsampling=2)
        print(f"✅ 已处理: {img_path.name} -> {out_path.name}")

def batch_process_images(in_dir: Path, out_dir: Path):
    files = [p for p in in_dir.iterdir() if p.suffix.lower() in EXTS]
    if not files:
        print("⚠️ 未找到可处理的图片")
        return
    for p in files:
        edit_image(p, out_dir / p.with_suffix(".jpg").name)

if __name__ == "__main__":
    batch_process_images(INPUT_DIR, OUTPUT_DIR)
