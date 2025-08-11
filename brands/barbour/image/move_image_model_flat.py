import os
import shutil
from collections import defaultdict

# ===== 参数配置 =====
SOURCE_DIR = r"D:\TB\Products\barbour\document\images_jacket"  # 原始图片目录
DIR_A = r"D:\TB\Products\barbour\document\images_jacket_model"                # 第1、2张图片
DIR_B = r"D:\TB\Products\barbour\document\images_jacket_flat"                # 最后一张图片

# 创建目标目录
os.makedirs(DIR_A, exist_ok=True)
os.makedirs(DIR_B, exist_ok=True)

# 用字典按商品编码分组
groups = defaultdict(list)

# 遍历文件并分组
for filename in os.listdir(SOURCE_DIR):
    if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        continue
    # 提取商品编码（编码是_之前的部分）
    code = filename.split("_")[0]
    groups[code].append(filename)

# 按文件名排序并移动
for code, files in groups.items():
    files.sort()  # 按文件名排序（假设数字顺序）
    if len(files) >= 1:
        # 第1张
        src_path = os.path.join(SOURCE_DIR, files[0])
        shutil.move(src_path, os.path.join(DIR_A, files[0]))
    if len(files) >= 2:
        # 第2张
        src_path = os.path.join(SOURCE_DIR, files[1])
        shutil.move(src_path, os.path.join(DIR_A, files[1]))
    if len(files) >= 3:
        # 最后一张
        src_path = os.path.join(SOURCE_DIR, files[-1])
        shutil.move(src_path, os.path.join(DIR_B, files[-1]))

print("🎯 处理完成！")
