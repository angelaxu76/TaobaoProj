from PIL import Image
import os

# 输入输出目录
input_dir = r"G:\temp\1"
output_dir = r"G:\temp\2"
os.makedirs(output_dir, exist_ok=True)

# 压缩目标大小（每张 < 500KB，5张合计<2MB）
target_size_kb = 500

def compress_image(file_path, output_path, quality=85, max_width=1500):
    img = Image.open(file_path)
    # 如果宽度太大，按比例缩放
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    # 循环降低质量，直到达到目标大小
    q = quality
    while True:
        img.save(output_path, "JPEG", optimize=True, quality=q)
        if os.path.getsize(output_path) <= target_size_kb * 1024 or q <= 60:
            break
        q -= 5

for file in os.listdir(input_dir):
    if file.lower().endswith(".jpg"):
        input_path = os.path.join(input_dir, file)
        output_path = os.path.join(output_dir, file)
        compress_image(input_path, output_path)
        print(f"✅ 压缩完成: {file}, 新大小 {os.path.getsize(output_path)/1024:.2f} KB")
