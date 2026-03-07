import os
from PIL import Image

def expand_to_square(img, fill_color=(255, 255, 255)):
    """
    将图片扩展成正方形，不剪切，只填充。
    fill_color: 填充颜色 (R, G, B)，默认白色。
    """
    width, height = img.size
    if width == height:
        return img
    size = max(width, height)
    new_img = Image.new("RGB", (size, size), fill_color)
    new_img.paste(img, ((size - width) // 2, (size - height) // 2))
    return new_img

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def process_folder(input_folder, output_folder=None, fill_color=(255, 255, 255),
                   recursive=False, quality=95):
    """
    遍历文件夹下所有图片：
    - webp / jpg / png → 统一转为 JPG
    - 扩展为正方形（白色填充）
    - recursive=True 时递归处理所有子目录（保留目录结构）
    - quality：JPEG 保存质量（建议 85~95，低于 65 电商平台可能拒绝）
    """
    from pathlib import Path

    src = Path(input_folder)
    dst = Path(output_folder) if output_folder else src

    pattern = "**/*" if recursive else "*"
    files = [p for p in src.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]

    ok = fail = 0
    for file_path in sorted(files):
        rel = file_path.relative_to(src)
        out_path = (dst / rel).with_suffix(".jpg")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with Image.open(file_path) as img:
                img = img.convert("RGB")
                square_img = expand_to_square(img, fill_color)
                square_img.save(out_path, "JPEG", quality=quality, optimize=True)
                ok += 1
                print(f"✅ {rel} → {out_path.name}")
        except Exception as e:
            fail += 1
            print(f"❌ {file_path.name}: {e}")

    print(f"\n完成：成功 {ok}，失败 {fail}，共 {ok + fail} 张")


if __name__ == "__main__":
    # ============================================================
    # 修改这里
    # ============================================================
    INPUT_DIR  = r"G:\temp\1"
    OUTPUT_DIR = r"G:\temp\2"
    RECURSIVE  = True    # True = 递归子目录（M&S 分组后的目录结构）
    QUALITY    = 90
    # ============================================================
    process_folder(INPUT_DIR, OUTPUT_DIR, fill_color=(255, 255, 255),
                   recursive=RECURSIVE, quality=QUALITY)
