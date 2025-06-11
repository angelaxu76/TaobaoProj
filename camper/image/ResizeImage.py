import os
from PIL import Image

# === 配置参数（统一集中管理） ===
INPUT_FOLDER = 'D:/TB/Products/camper/ready_to_publish/images/'
OUTPUT_FOLDER = 'D:/TB/Products/camper/ready_to_publish/square_images/'
BACKGROUND_COLOR = (255, 255, 255)  # 白色背景

def expand_to_square(img, background_color=(255, 255, 255)):
    """
    将图片扩展为正方形，居中显示，其余部分用背景色填充
    """
    width, height = img.size
    if width == height:
        return img

    max_side = max(width, height)
    new_img = Image.new('RGB', (max_side, max_side), background_color)
    paste_position = ((max_side - width) // 2, (max_side - height) // 2)
    new_img.paste(img, paste_position)
    return new_img

def process_folder(input_folder, output_folder, background_color=(255, 255, 255)):
    """
    批量处理文件夹下的图片
    """
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
                    print(f"✅ 已处理: {filename}")
            except Exception as e:
                print(f"❌ 处理 {filename} 时出错: {e}")

def main():
    process_folder(INPUT_FOLDER, OUTPUT_FOLDER, BACKGROUND_COLOR)

if __name__ == "__main__":
    main()
