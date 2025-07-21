import os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

def merge_images_grid(img_files, export_file, product_name, width=750, margin=10, gap=10, title_height=150):
    """
    img_files: 图片路径列表
    export_file: 输出文件路径
    product_name: 商品标题
    width: 画布总宽度（默认750）
    margin: 边距（默认10px）
    gap: 图片之间的间距（默认10px）
    title_height: 标题区域高度（默认150px）
    """

    # 每列图片宽度
    img_size = (width - margin * 2 - gap) // 2  # (750 - 20 - 10) / 2 = 360
    num_images = len(img_files)
    rows = (num_images + 1) // 2  # 每行两列

    # 总高度 = 标题高度 + 图片行数 * (图片高度 + 间距) + 底部边距
    total_height = title_height + rows * img_size + (rows - 1) * gap + margin

    # 创建白底画布
    dest_img = Image.new("RGB", (width, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(dest_img)

    # 绘制标题
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()
    draw.text((margin, 50), product_name, font=font, fill=(0, 0, 0))

    # 起始 Y 坐标
    y_offset = title_height

    # 布局：两列
    for i, img_file in enumerate(img_files):
        img = Image.open(img_file).convert("RGB")
        img_resized = img.resize((img_size, img_size))

        if i % 2 == 0:  # 左列
            x = margin
        else:  # 右列
            x = margin + img_size + gap

        dest_img.paste(img_resized, (x, y_offset))

        # 换行
        if i % 2 == 1:
            y_offset += img_size + gap

    # 如果奇数，最后一张图片独占一行，仍然放在左边
    if num_images % 2 == 1:
        y_offset += img_size + gap

    dest_img.save(export_file, quality=95)
    print(f"✅ 合并完成: {export_file}")


def batch_merge_images(brand_config, width=750):
    image_dir = brand_config["IMAGE_CUTTER"]
    merged_dir = brand_config["MERGED_DIR"]

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
