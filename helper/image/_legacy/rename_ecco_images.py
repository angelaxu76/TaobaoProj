import os

# 替换为你的图片目录路径
IMAGE_DIR = r"D:\TB\Products\ECCO\document\image_defence"

def rename_images(directory):
    for filename in os.listdir(directory):
        if "-" in filename:
            # 只替换第一个 -
            new_name = filename.replace("-", "", 1)
            old_path = os.path.join(directory, filename)
            new_path = os.path.join(directory, new_name)
            # 避免重名覆盖
            if not os.path.exists(new_path):
                os.rename(old_path, new_path)
                print(f"✅ 重命名: {filename} → {new_name}")
            else:
                print(f"⚠️ 已存在，跳过: {new_name}")

rename_images(IMAGE_DIR)
