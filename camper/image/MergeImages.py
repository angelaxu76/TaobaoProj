import os
from pathlib import Path
from PIL import Image, ImageDraw
from collections import defaultdict

# === 参数设置 ===
IMAGE_DIR = Path(r"D:\TB\Products\camper\BACKUP\20250505\square_images")
OUTPUT_DIR = Path(r"D:\TB\Products\camper\BACKUP\20250505\merges")
OUTPUT_WIDTH = 750
PADDING = 10  # 四周和图片间距
MAX_COLS = 2  # 每行最多显示2张图片

# 每张图片尺寸 = (750 - 3*padding) // 2
BOX_WIDTH = BOX_HEIGHT = (OUTPUT_WIDTH - (MAX_COLS + 1) * PADDING) // MAX_COLS

# 创建输出目录
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === 按商品编码分组 ===
image_groups = defaultdict(list)
for filename in os.listdir(IMAGE_DIR):
    if filename.lower().endswith(".jpg"):
        parts = filename.split("_")
        if len(parts) >= 2:
            code = parts[0]  # e.g., K201608-012
            image_groups[code].append(IMAGE_DIR / filename)

# === 合成函数 ===
def merge_images(code, img_paths):
    img_paths.sort()
    total = len(img_paths)
    has_last_centered = (total % 2 == 1)
    base_rows = total // 2  # 不包含最后那张的大图
    extra_space = 730 + PADDING if has_last_centered else 0

    # 总画布高度：前几行小图 + 最后一张大图（如有）
    canvas_height = base_rows * BOX_HEIGHT + (base_rows + 1) * PADDING + extra_space

    canvas = Image.new("RGB", (OUTPUT_WIDTH, canvas_height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    for idx, img_path in enumerate(img_paths):
        is_last = (idx == total - 1)
        if is_last and has_last_centered:
            # 最后一张大图，730x730，居中
            img = Image.open(img_path).resize((730, 730))
            x = (OUTPUT_WIDTH - 730) // 2
            y = canvas_height - 730 - PADDING
            canvas.paste(img, (x, y))

        else:
            img = Image.open(img_path).resize((BOX_WIDTH, BOX_HEIGHT))
            row = idx // 2
            col = idx % 2
            x = PADDING if col == 0 else PADDING * 2 + BOX_WIDTH
            y = PADDING + row * (BOX_HEIGHT + PADDING)
            canvas.paste(img, (x, y))


    canvas.save(OUTPUT_DIR / f"{code}_merged.jpg")

# === 执行合并 ===
for code, paths in image_groups.items():
    merge_images(code, paths)

print("✅ 图片合并完成，输出目录：", OUTPUT_DIR)
