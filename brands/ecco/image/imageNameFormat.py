import os
import re
from pathlib import Path

# === 配置图片目录 ===
IMAGE_DIR = Path(r"D:\TB\Products\ECCO\publication\square_images")

# === 支持的图片扩展名
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# === 开始处理 ===
for file in IMAGE_DIR.glob("*"):
    if file.suffix.lower() not in VALID_EXTENSIONS:
        continue

    # 匹配带有中间“-”的商品编码，例如 091504-01007 或 470824-61143
    match = re.match(r"(\d{6})-(\d{5})(.*)", file.stem)
    if match:
        new_stem = f"{match.group(1)}{match.group(2)}{match.group(3)}"
        new_name = new_stem + file.suffix
        new_path = file.with_name(new_name)

        os.rename(file, new_path)
        print(f"✅ 已重命名: {file.name} → {new_name}")
    else:
        print(f"⏭️ 跳过未匹配文件: {file.name}")
