import os
import shutil

# 原始图片目录
source_dir = r"C:\Users\Maddingzhou\Desktop\ECCO\image_process"

# 目标根目录（可以修改为其他路径）
target_root_dir = r"C:\Users\Maddingzhou\Desktop\ECCO\image_process分组图片"

# 分成几组（图片平均分配到各组）
num_groups = 5

# 支持的图片扩展名
image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

# 获取所有图片文件（忽略大小写），排序保证结果稳定
files = sorted(f for f in os.listdir(source_dir) if os.path.splitext(f)[1].lower() in image_extensions)

total_files = len(files)
if total_files == 0:
    print("没有找到图片，退出。")
    raise SystemExit

# 组数不能超过图片数
num_groups = max(1, min(num_groups, total_files))

# 平均分配：前 remainder 组各多 1 张
base_size, remainder = divmod(total_files, num_groups)

print(f"总图片数: {total_files}")
print(f"分成 {num_groups} 组，每组 {base_size}~{base_size + (1 if remainder else 0)} 张")

start_index = 0
for i in range(num_groups):
    size = base_size + (1 if i < remainder else 0)
    group_files = files[start_index:start_index + size]
    start_index += size

    group_dir = os.path.join(target_root_dir, f'group_{i + 1}')
    os.makedirs(group_dir, exist_ok=True)

    for file_name in group_files:
        shutil.copy2(os.path.join(source_dir, file_name), os.path.join(group_dir, file_name))

    print(f"已复制第 {i + 1} 组: {len(group_files)} 张图片 -> {group_dir}")

print("全部分组完成！")
