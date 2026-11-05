from PIL import Image, ImageDraw, ImageFont, ImageOps
from pathlib import Path
import os
from collections import defaultdict


def merge_images_grid(img_files, export_file, product_name, width=750, margin=10, gap=10, title_height=150,
                      keep_aspect=False):
    """keep_aspect=True：格子按第一张图的比例排版（长方形图不被压成正方形）；默认格子为正方形。"""
    img_size = (width - margin * 2 - gap) // 2
    num_images = len(img_files)
    is_odd = (num_images % 2 == 1)

    ratio = 1.0
    if keep_aspect:
        with Image.open(img_files[0]) as first:
            ratio = first.height / first.width
    cell = (img_size, round(img_size * ratio))
    big_size = img_size * 2 + gap
    big_cell = (big_size, round(big_size * ratio))

    def load(path, size):
        img = Image.open(path).convert("RGB")
        return ImageOps.pad(img, size, color=(255, 255, 255)) if keep_aspect else img.resize(size)

    last_row_extra_height = big_cell[1] if is_odd else 0
    rows = num_images // 2
    total_height = title_height + rows * (cell[1] + gap) + last_row_extra_height + margin

    dest_img = Image.new("RGB", (width, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(dest_img)

    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()
    draw.text((margin, 50), product_name, font=font, fill=(0, 0, 0))

    y_offset = title_height
    i = 0
    while i < num_images:
        if i == num_images - 1 and is_odd:
            dest_img.paste(load(img_files[i], big_cell), (margin, y_offset))
            y_offset += big_cell[1] + gap
            i += 1
        else:
            dest_img.paste(load(img_files[i], cell), (margin, y_offset))
            if i + 1 < num_images:
                dest_img.paste(load(img_files[i + 1], cell), (margin + img_size + gap, y_offset))
            y_offset += cell[1] + gap
            i += 2

    dest_img.save(export_file, quality=95)
    print(f"✅ 合并完成: {export_file}")


def batch_merge_images(image_dirs, merged_dir, width=750, keep_aspect=False):
    # 支持传入单个目录，或多个目录组成的列表/元组（同一编码的图会跨目录合并到一起）
    if isinstance(image_dirs, (str, Path)):
        image_dirs = [image_dirs]

    merged_dir = Path(merged_dir)
    merged_dir.mkdir(parents=True, exist_ok=True)

    groups = defaultdict(list)
    for image_dir in image_dirs:
        image_dir = Path(image_dir)

        # 如果输入目录不存在，自动创建一个空目录
        if not image_dir.exists():
            print(f"⚠️ 输入目录不存在，已创建空目录: {image_dir}")
            image_dir.mkdir(parents=True, exist_ok=True)
            continue

        for filename in os.listdir(image_dir):
            if filename.lower().endswith(".jpg"):
                code = Path(filename).stem.split('_')[0]
                groups[code].append(str(image_dir / filename))

    for code, files in groups.items():
        files.sort()
        export_file = merged_dir / f"{code}_merged.jpg"
        merge_images_grid(files, str(export_file), code, width=width, keep_aspect=keep_aspect)



# ========= main 入口 =========
def main():
    DEFAULT_INPUT = Path(r"D:\Projects\TaobaoProj\images_trimmed")   # 输入目录（按需改）
    DEFAULT_OUTPUT = Path(r"/images_merged")   # 输出目录（按需改）
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"▶ 合并图片: {DEFAULT_INPUT} → {DEFAULT_OUTPUT}")
    batch_merge_images(DEFAULT_INPUT, DEFAULT_OUTPUT, width=750)


if __name__ == "__main__":
    main()
