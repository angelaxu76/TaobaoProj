from PIL import Image
import os
from pathlib import Path

# === 配置项 ===
IMAGE_DIR = Path(r"D:\TB\Products\marksandspencer\publication\linkfox_output_1")  # 替换为你的目录
MAX_WIDTH = 1500

def resize_image(image_path: Path):
    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # 如果图片宽度小于等于 1500，则跳过
            if width <= MAX_WIDTH:
                return False

            # 等比例缩放
            new_height = int(height * MAX_WIDTH / width)
            resized_img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

            # 保存，覆盖原图（统一转 JPEG，兼容扩展名为 .jpg 但实为 WEBP 等格式的文件）
            if resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            resized_img.save(image_path, format='JPEG', quality=95, optimize=True)
            print(f"✅ 已处理: {image_path.name} -> {MAX_WIDTH}px")
            return True
    except Exception as e:
        print(f"❌ 处理失败: {image_path.name}, 错误: {e}")
        return False

def batch_resize_images(directory: Path):
    count = 0
    for file in directory.glob("*"):
        if file.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            if resize_image(file):
                count += 1
    print(f"\n🎉 处理完成，共压缩 {count} 张图片")

if __name__ == "__main__":
    batch_resize_images(IMAGE_DIR)
