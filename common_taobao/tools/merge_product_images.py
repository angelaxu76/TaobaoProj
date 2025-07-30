import os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

def merge_images_grid(img_files, export_file, product_name, width=750, margin=10, gap=10, title_height=150):
    from PIL import Image, ImageDraw, ImageFont

    img_size = (width - margin * 2 - gap) // 2
    num_images = len(img_files)
    is_odd = (num_images % 2 == 1)

    # 最后一张大图高度等于两列宽度（为正方形）
    last_row_extra_height = (img_size * 2 + gap) if is_odd else 0
    rows = num_images // 2
    total_height = title_height + rows * (img_size + gap) + last_row_extra_height + margin

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
            # 最后一张大图（正方形），宽 = 2张图 + gap，高 = 同宽
            img = Image.open(img_files[i]).convert("RGB")

            big_size = img_size * 2 + gap
            img = img.resize((big_size, big_size))  # 放大为正方形

            dest_img.paste(img, (margin, y_offset))
            y_offset += big_size + gap
            i += 1
        else:
            # 左图
            img1 = Image.open(img_files[i]).convert("RGB").resize((img_size, img_size))
            dest_img.paste(img1, (margin, y_offset))
            # 右图
            if i + 1 < num_images:
                img2 = Image.open(img_files[i + 1]).convert("RGB").resize((img_size, img_size))
                dest_img.paste(img2, (margin + img_size + gap, y_offset))
            y_offset += img_size + gap
            i += 2

    dest_img.save(export_file, quality=95)
    print(f"✅ 合并完成: {export_file}")





def batch_merge_images(image_dir, merged_dir, width=750):
    from collections import defaultdict
    import os

    os.makedirs(merged_dir, exist_ok=True)

    # 按编码分组
    groups = defaultdict(list)
    for filename in os.listdir(image_dir):
        if filename.lower().endswith(".jpg"):
            code = filename.split('_')[0]
            groups[code].append(os.path.join(image_dir, filename))

    for code, files in groups.items():
        files.sort()
        export_file = os.path.join(merged_dir, f"{code}_merged.jpg")
        merge_images_grid(files, export_file, code, width=width)



if __name__ == "__main__":
    from config import CAMPER
    batch_merge_images(CAMPER, width=750)
