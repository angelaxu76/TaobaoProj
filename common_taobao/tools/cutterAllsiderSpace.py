import os
import glob
from PIL import Image

def trim_sides(image, tolerance=5):
    """
    裁剪图片左右无内容区域。
    :param image: PIL Image 对象
    :param tolerance: 容差值（暂时未启用，可扩展颜色相近判断）
    :return: 裁剪后的 Image 对象
    """
    img = image.convert("RGB")  # 转换为RGB，避免RGBA影响
    width, height = img.size
    pixels = img.load()

    # 计算左侧裁剪边界
    left = 0
    for x in range(width):
        if any(pixels[x, y] != pixels[0, y] for y in range(height)):
            left = x
            break

    # 计算右侧裁剪边界
    right = width
    for x in range(width - 1, -1, -1):
        if any(pixels[x, y] != pixels[width - 1, y] for y in range(height)):
            right = x + 1
            break

    if left >= right:  # 防止裁剪范围错误
        return image
    return img.crop((left, 0, right, height))


def trim_images_in_folder(input_folder, output_folder, file_pattern="*.*", tolerance=5):
    """
    批量裁剪图片左右空白区域。
    :param input_folder: 输入文件夹路径
    :param output_folder: 输出文件夹路径
    :param file_pattern: 文件匹配模式（如 "*.jpg", "*.png"）
    :param tolerance: 容差值（当前逻辑未使用）
    """
    # 检查输入文件夹
    if not os.path.exists(input_folder):
        print(f"❌ 输入文件夹不存在: {input_folder}")
        return

    # 创建输出文件夹
    os.makedirs(output_folder, exist_ok=True)

    # 遍历文件
    file_list = glob.glob(os.path.join(input_folder, file_pattern))
    if not file_list:
        print(f"⚠️ 未找到匹配文件: {file_pattern} in {input_folder}")
        return

    print(f"开始处理 {len(file_list)} 张图片...")
    for filepath in file_list:
        try:
            with Image.open(filepath) as img:
                trimmed_img = trim_sides(img, tolerance)
                filename = os.path.basename(filepath)
                output_path = os.path.join(output_folder, filename)
                trimmed_img.save(output_path)
                print(f"✅ 已裁剪并保存: {output_path}")
        except Exception as e:
            print(f"❌ 处理图片 {filepath} 时出错: {e}")

    print("✅ 所有图片处理完成！")


# ✅ 命令行调用（可选）
if __name__ == "__main__":
    # 示例：python trim_images.py "D:/input" "D:/output" "*.png" 5
    import sys
    if len(sys.argv) < 3:
        print("用法: python trim_images.py <输入文件夹> <输出文件夹> [文件模式] [容差]")
    else:
        input_dir = sys.argv[1]
        output_dir = sys.argv[2]
        pattern = sys.argv[3] if len(sys.argv) > 3 else "*.*"
        tolerance = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        trim_images_in_folder(input_dir, output_dir, pattern, tolerance)
