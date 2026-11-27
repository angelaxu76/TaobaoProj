import os
import random
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
import numpy as np
from config import CAMPER

# === 输入输出路径配置 ===
INPUT_DIR = Path(CAMPER["IMAGE_DOWNLOAD"])
OUTPUT_DIR = Path(CAMPER["IMAGE_PROCESS"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 图像处理参数 ===
ROTATE_RANGE = (-2, 2)            # 旋转角度范围（度）
CROP_PERCENT = (0.5, 1.5)         # 裁剪百分比范围（上下左右）
BORDER_PADDING = 20               # 白边像素
NOISE_AMPLITUDE = 3               # 噪点幅度（±像素值，均值为 0）
# 亮度/对比度只往上调：< 1 会把白底整体压暗成浅灰（原来噪点层 + 0.97 系数会让 255 变成 ~246）
BRIGHTNESS_RANGE = (1.00, 1.03)
CONTRAST_RANGE = (1.00, 1.03)

def add_noise_layer(img: Image.Image) -> Image.Image:
    """叠加均值为 0 的随机噪点，扰乱图像指纹（不改变整体亮度，白底仍为白色）"""
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    noise = np.random.randint(-NOISE_AMPLITUDE, NOISE_AMPLITUDE + 1, arr.shape, dtype=np.int16)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "RGB")

def safe_crop(img: Image.Image, crop_percent=1.0):
    """安全裁剪四周，避免裁掉主体"""
    w, h = img.size
    dx = int(w * crop_percent / 100)
    dy = int(h * crop_percent / 100)
    return img.crop((dx, dy, w - dx, h - dy))

def edit_image(img_path: Path, out_path: Path):
    with Image.open(img_path) as img:
        img = img.convert("RGB")

        # 1️⃣ 添加白边
        img = ImageOps.expand(img, border=BORDER_PADDING, fill=(255, 255, 255))

        # 2️⃣ 随机旋转
        angle = random.uniform(*ROTATE_RANGE)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))

        # 3️⃣ 随机水平翻转
        img = ImageOps.mirror(img)

        # 4️⃣ 裁剪边缘
        crop_percent = random.uniform(*CROP_PERCENT)
        img = safe_crop(img, crop_percent)

        # 5️⃣ 亮度 & 对比度微调
        img = ImageEnhance.Brightness(img).enhance(random.uniform(*BRIGHTNESS_RANGE))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(*CONTRAST_RANGE))

        # 6️⃣ 添加噪点扰动
        img = add_noise_layer(img)

        # 7️⃣ 保存最终图像
        img = img.convert("RGB")
        img.save(out_path, quality=90)
        print(f"✅ 已处理: {img_path.name}")

def batch_process_images(INPUT_DIR, OUTPUT_DIR):
    for file in INPUT_DIR.glob("*.jpg"):
        out_file = OUTPUT_DIR / file.name
        try:
            edit_image(file, out_file)
        except (UnidentifiedImageError, OSError) as e:
            print(f"⚠️ 跳过无效图片: {file.name}（{e}）")

if __name__ == "__main__":
    batch_process_images()
