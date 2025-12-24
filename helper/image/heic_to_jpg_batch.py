import os
from PIL import Image
import pillow_heif

# 注册 HEIC/HEIF 支持
pillow_heif.register_heif_opener()


def convert_heic_to_jpg(
    input_dir: str,
    output_dir: str,
    target_size_mb: float = 1.0,
    max_width: int = 3000
):
    """
    将 input_dir 中的 HEIC/HEIF 图片转为 JPG，
    并压缩到接近 target_size_mb（默认 1MB）以内，
    输出到 output_dir

    :param input_dir: HEIC 图片目录
    :param output_dir: JPG 输出目录
    :param target_size_mb: 目标大小（MB）
    :param max_width: 最大宽度（超过则等比缩放）
    """

    os.makedirs(output_dir, exist_ok=True)
    target_bytes = int(target_size_mb * 1024 * 1024)

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith((".heic", ".heif")):
            continue

        input_path = os.path.join(input_dir, filename)
        output_name = os.path.splitext(filename)[0] + ".jpg"
        output_path = os.path.join(output_dir, output_name)

        with Image.open(input_path) as img:
            img = img.convert("RGB")

            # 等比缩放（防止 48MP 原图太大）
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # 二分法压缩质量，逼近目标大小
            low, high = 30, 95
            best_quality = high

            while low <= high:
                mid = (low + high) // 2
                img.save(output_path, "JPEG", quality=mid, optimize=True)

                size = os.path.getsize(output_path)
                if size > target_bytes:
                    high = mid - 1
                else:
                    best_quality = mid
                    low = mid + 1

            # 最终保存
            img.save(output_path, "JPEG", quality=best_quality, optimize=True)

        print(f"✅ {filename} → {output_name} ({os.path.getsize(output_path)/1024/1024:.2f} MB)")
