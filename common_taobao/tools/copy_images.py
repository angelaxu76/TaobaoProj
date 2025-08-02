import shutil
from pathlib import Path

def copy_images(src_dir: Path, dst_dir: Path):
    # 检查目标目录是否存在，不存在则创建
    dst_dir.mkdir(parents=True, exist_ok=True)

    # 支持的图片扩展名
    image_extensions = {".jpg", ".jpeg", ".png"}

    count = 0
    for file in src_dir.glob("*"):
        if file.suffix.lower() in image_extensions:
            target_file = dst_dir / file.name
            shutil.copyfile(file, target_file)
            count += 1
            print(f"✅ 复制: {file.name}")

    print(f"\n🎉 完成，共复制 {count} 张图片")

# === 使用示例 ===
if __name__ == "__main__":
    src = Path("D:/TB/Products/clarks_jingya/document/images")
    dst = Path("D:/TB/Products/clarks_jingya/publication/html/images")

    copy_images(src, dst)
