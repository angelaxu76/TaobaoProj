import os
import shutil
from math import ceil

# 原始图片目录
source_dir = r"D:\TB\Products\ECCO\repulibcation\英国伦敦代购2015\images"

# 目标根目录（可以修改为其他路径）
target_root_dir = r"D:\TB\Products\ECCO\repulibcation\英国伦敦代购2015\images分组图片"

# 每组的图片数量
group_size = 200

# 支持的图片扩展名
image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

# 获取所有图片文件（忽略大小写）
files = [f for f in os.listdir(source_dir) if os.path.splitext(f)[1].lower() in image_extensions]

total_files = len(files)
num_groups = ceil(total_files / group_size)

print(f"总图片数: {total_files}")
print(f"需要分成 {num_groups} 组，每组 {group_size} 张")

# 分组复制文件
for i in range(num_groups):
    group_dir = os.path.join(target_root_dir, f'group_{i + 1}')
    os.makedirs(group_dir, exist_ok=True)

    # 当前组图片
    start_index = i * group_size
    end_index = min(start_index + group_size, total_files)
    group_files = files[start_index:end_index]

    for file_name in group_files:
        src_path = os.path.join(source_dir, file_name)
        dst_path = os.path.join(group_dir, file_name)

        # 复制文件
        shutil.copy2(src_path, dst_path)

    print(f"已复制第 {i + 1} 组: {len(group_files)} 张图片 -> {group_dir}")

print("全部分组完成！")
