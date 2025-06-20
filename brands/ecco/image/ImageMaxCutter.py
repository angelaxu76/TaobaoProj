
import os
import shutil
from datetime import datetime
from PIL import Image, ImageOps
import cv2
import numpy as np

# =====================================
# 可配置变量
# =====================================
INPUT_FOLDER = r"D:\TB\Products\ECCO\document\images"              # 原始图片文件夹
PROCESSED_FOLDER = r"D:\TB\Products\ECCO\document\processed_images" # 翻转 + JPG 输出
SQUARE_FOLDER = r"D:\TB\Products\ECCO\document\square_images"       # 最大化裁剪 + 正方形输出

SUPPORTED_IMAGE_FORMATS = ('.webp', '.jpg', '.jpeg', '.png')

# =====================================
# 工具函数
# =====================================
def create_backup(input_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(input_dir, f"backup_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.lower().endswith('.webp'):
            shutil.copy2(os.path.join(input_dir, filename), os.path.join(backup_dir, filename))

    print(f"✅ 已备份原始图片到: {backup_dir}")
    return backup_dir

def convert_webp_to_jpg_flip(input_path, output_path):
    try:
        with Image.open(input_path) as img:
            img = img.convert("RGBA")
            img = ImageOps.mirror(img)
            white_bg = Image.new("RGB", img.size, (255, 255, 255))
            alpha = img.split()[-1]
            white_bg.paste(img.convert("RGB"), mask=alpha)
            white_bg.save(output_path, format="JPEG", quality=95)
            print(f"✅ 转换并保存 JPG: {output_path}")
    except Exception as e:
        print(f"❌ 处理图片失败: {input_path}，错误信息: {e}")

def batch_convert_webp_to_jpg(input_folder, output_folder):
    create_backup(input_folder)
    os.makedirs(output_folder, exist_ok=True)
    for filename in os.listdir(input_folder):
        if filename.lower().endswith('.webp'):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".jpg")
            convert_webp_to_jpg_flip(input_path, output_path)
    print("\n🚀 批量转换 JPG 完成！")

def resize_to_square(image_path, output_path):
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ 无法读取图片: {image_path}")
        return
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, threshold = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
    threshold = cv2.bitwise_not(threshold)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print(f"❗ 没有检测到有效轮廓: {image_path}")
        return
    x_min = y_min = float('inf')
    x_max = y_max = 0
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        x_min = min(x_min, x)
        y_min = min(y_min, y)
        x_max = max(x_max, x + w)
        y_max = max(y_max, y + h)
    cropped_img = img[y_min:y_max, x_min:x_max]
    ch, cw = cropped_img.shape[:2]
    size = max(ch, cw)
    square_img = np.ones((size, size, 3), dtype=np.uint8) * 255
    xo = (size - cw) // 2
    yo = (size - ch) // 2
    square_img[yo:yo + ch, xo:xo + cw] = cropped_img
    rgb_img = cv2.cvtColor(square_img, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb_img).save(output_path, format="JPEG", quality=95)
    print(f"✅ 保存为正方形图片: {output_path}")

def process_images_in_folder(input_folder, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(SUPPORTED_IMAGE_FORMATS):
            resize_to_square(
                os.path.join(input_folder, filename),
                os.path.join(output_folder, os.path.splitext(filename)[0] + ".jpg")
            )
    print("\n🚀 所有图片最大化裁剪 + 正方形 完成！")

def main():
    batch_convert_webp_to_jpg(INPUT_FOLDER, PROCESSED_FOLDER)
    process_images_in_folder(PROCESSED_FOLDER, SQUARE_FOLDER)

if __name__ == "__main__":
    main()
