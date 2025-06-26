import os
from PIL import Image
from config import CAMPER

def expand_to_square(img, background_color=(255, 255, 255)):
    """
    将图片扩展为正方形，居中显示，其余部分用背景色填充
    """
    width, height = img.size
    if width == height:
        return img  # 已经是正方形，直接返回

    max_side = max(width, height)
    # 创建一个新图像，背景色可自定义
    new_img = Image.new('RGB', (max_side, max_side), background_color)
    # 计算粘贴位置，使原图居中
    paste_position = ((max_side - width) // 2, (max_side - height) // 2)
    new_img.paste(img, paste_position)
    return new_img

def process_folder(input_folder, output_folder, background_color=(255, 255, 255)):
    """
    批量处理文件夹下的图片
    """
    # 确保输出文件夹存在
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(supported_formats):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)

            try:
                with Image.open(input_path) as img:
                    img_converted = expand_to_square(img, background_color)
                    img_converted.save(output_path)
                    print(f"已处理: {filename}")
            except Exception as e:
                print(f"处理 {filename} 时出错: {e}")

# 使用方法
input_folder = CAMPER["DEF_IMAGE_DIR"]   # 例如：'./images'
output_folder = CAMPER["IMAGE_DIR"]  # 例如：'./square_images'

process_folder(input_folder, output_folder)
