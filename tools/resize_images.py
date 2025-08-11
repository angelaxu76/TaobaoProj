import os
from PIL import Image, ImageOps

def resize_images_to_width150(folder_path):
    output_folder = os.path.join(folder_path, "resized")
    os.makedirs(output_folder, exist_ok=True)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            filepath = os.path.join(folder_path, filename)
            try:
                with Image.open(filepath) as img:
                    # 转换为RGB（避免透明图缩放失真）
                    img = img.convert("RGB")

                    # 保持比例，目标宽度 150
                    orig_width, orig_height = img.size
                    if orig_width == 150:
                        resized_img = img.copy()
                        print(f"ℹ️ {filename} already 150px wide.")
                    else:
                        w_percent = 150 / float(orig_width)
                        new_height = int(orig_height * w_percent)
                        resized_img = img.resize((150, new_height), Image.LANCZOS)

                    output_path = os.path.join(output_folder, filename)
                    resized_img.save(output_path, quality=95)
                    print(f"✅ {filename} → resized to 150x{new_height}")
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")

# 使用示例
resize_images_to_width150(r"D:\Images")
