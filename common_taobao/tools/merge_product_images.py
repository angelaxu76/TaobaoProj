import os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from config import CLARKS, CAMPER, ECCO, GEOX  # 假设 config.py 已定义这些品牌配置

# =========================
# 通用核心函数
# =========================
def merge_images(img_files, export_file, splitor_file, product_name, mode='single', width=750):
    """
    img_files: 图片路径列表
    export_file: 输出文件路径
    splitor_file: 分割图路径
    product_name: 商品标题
    mode: 'single'（单列）或 'double'（双列）
    width: 总宽度，默认 750
    """
    splitor_img = Image.open(splitor_file).convert("RGB")
    splitor_height = 30

    # 获取图片比例
    first_img = Image.open(img_files[0])
    img_w, img_h = first_img.size

    # 缩放规则
    if mode == 'single':
        col_width = width - 20
        scale_height = lambda h: int(h * col_width / img_w)
    else:  # double
        col_width = (width - 30) // 2
        scale_height = lambda h: int(h * col_width / img_w)

    # 计算总高度
    if mode == 'single':
        total_height = splitor_height + 150 + sum(scale_height(img_h) for _ in img_files) + 10 * len(img_files)
    else:
        rows = (len(img_files) + 1) // 2
        avg_h = scale_height(img_h)
        total_height = splitor_height + 150 + rows * (avg_h + 10)

    # 创建白底画布
    dest_img = Image.new("RGB", (width, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(dest_img)

    # 绘制分割图
    splitor_resized = splitor_img.resize((width, splitor_height))
    dest_img.paste(splitor_resized, (0, 0))

    # 绘制标题
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except:
        font = ImageFont.load_default()
    draw.text((50, 100), product_name, font=font, fill=(0, 0, 0))

    # 插入图片
    y_offset = splitor_height + 150
    if mode == 'single':
        for img_file in img_files:
            img = Image.open(img_file)
            h = scale_height(img.height)
            img_resized = img.resize((col_width, h))
            dest_img.paste(img_resized, (10, y_offset))
            y_offset += h + 10
    else:
        x_left, x_right = 10, width // 2 + 5
        for i, img_file in enumerate(img_files):
            img = Image.open(img_file)
            h = scale_height(img.height)
            img_resized = img.resize((col_width, h))
            if i % 2 == 0:
                dest_img.paste(img_resized, (x_left, y_offset))
            else:
                dest_img.paste(img_resized, (x_right, y_offset))
                y_offset += h + 10
        if len(img_files) % 2 == 1:
            y_offset += avg_h + 10

    dest_img.save(export_file, quality=95)
    print(f"✅ 合并完成: {export_file}")


# =========================
# 批量处理通用函数
# =========================
def batch_merge_images(brand_config, mode='single', width=750):
    image_dir = brand_config["IMAGE_DIR"]
    merged_dir = brand_config["MERGED_DIR"]
    splitor_file = os.path.join(brand_config["ASSETS_DIR"], "splitor.jpg")

    os.makedirs(merged_dir, exist_ok=True)

    # 按编码分组
    groups = defaultdict(list)
    for filename in os.listdir(image_dir):
        if filename.lower().endswith(".jpg"):
            code = filename.split('_')[0]  # 去掉 _C/_F 后缀
            groups[code].append(os.path.join(image_dir, filename))

    # 每组生成合并图
    for code, files in groups.items():
        files.sort()  # 保证顺序
        export_file = os.path.join(merged_dir, f"{code}.jpg")
        merge_images(files, export_file, splitor_file, code, mode=mode, width=width)


if __name__ == "__main__":
    # ✅ 批量合并 Camper 图片，模式 single，宽 750
    from config import CAMPER
    batch_merge_images(CAMPER, mode='single', width=750)

    # ✅ 如果要处理 CLARKS / ECCO，只需调用：
    # from config import CLARKS
    # batch_merge_images(CLARKS, mode='double', width=750)
