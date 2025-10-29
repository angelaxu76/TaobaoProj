import os
from PIL import Image

def expand_to_square(img, background_color=(255, 255, 255)):
    width, height = img.size
    if width == height:
        return img
    max_side = max(width, height)
    new_img = Image.new('RGB', (max_side, max_side), background_color)
    paste_position = ((max_side - width) // 2, (max_side - height) // 2)
    new_img.paste(img, paste_position)
    return new_img

def expand_images_in_folder(input_folder, output_folder, background_color=(255, 255, 255)):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
    count = 0

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(supported_formats):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)

            try:
                with Image.open(input_path) as img:
                    img_converted = expand_to_square(img, background_color)
                    img_converted.save(output_path)
                    count += 1
            except Exception as e:
                print(f"❌ 处理 {filename} 出错: {e}")
    print(f"✅ 已处理图片数量: {count}")
