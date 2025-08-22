import os
from PIL import Image

def expand_to_square(img, fill_color=(255, 255, 255)):
    """
    将图片扩展成正方形，不剪切，只填充。
    fill_color: 填充颜色 (R, G, B)，默认白色。
    """
    width, height = img.size
    if width == height:
        return img
    size = max(width, height)
    new_img = Image.new("RGB", (size, size), fill_color)
    new_img.paste(img, ((size - width) // 2, (size - height) // 2))
    return new_img

def process_folder(input_folder, output_folder=None, fill_color=(255, 255, 255)):
    """
    遍历文件夹下所有图片：
    - 如果是 webp，先转换为 jpg
    - 再将图片扩展为正方形
    """
    if output_folder is None:
        output_folder = input_folder
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for filename in os.listdir(input_folder):
        file_path = os.path.join(input_folder, filename)
        if not os.path.isfile(file_path):
            continue

        # 支持的图片格式
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
            with Image.open(file_path) as img:
                img = img.convert("RGB")  # 统一为 RGB 格式
                square_img = expand_to_square(img, fill_color)

                # 如果是 webp，强制保存为 JPG
                if filename.lower().endswith('.webp'):
                    new_filename = os.path.splitext(filename)[0] + ".jpg"
                else:
                    new_filename = os.path.splitext(filename)[0] + ".jpg"

                output_path = os.path.join(output_folder, new_filename)
                square_img.save(output_path, "JPEG", quality=95)
                print(f"✅ 已处理并保存为 JPG：{new_filename}")

if __name__ == "__main__":
    input_dir = r"D:\TB\Products\barbour\repulibcation\images"  # 修改为你的图片文件夹路径
    output_dir = r"D:\TB\Products\barbour\repulibcation\imagesSQUARE"  # 如果想覆盖原图，可以设为 None
    process_folder(input_dir, output_dir, fill_color=(255, 255, 255))  # 白色填充
