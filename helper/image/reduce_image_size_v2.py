import os
import shutil
from pathlib import Path
from PIL import Image

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def process_one(input_dir: str, output_dir: str, target_kb: int = 1024):
    """
    处理 input_dir 下的所有图片，输出到 output_dir
    - <= target_kb：原样复制（完全无损）
    - > target_kb：压缩后输出
    """

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for root, _, files in os.walk(input_dir):
        root_path = Path(root)
        rel_dir = root_path.relative_to(input_dir)
        out_root = output_dir / rel_dir
        out_root.mkdir(parents=True, exist_ok=True)

        for fn in files:
            in_path = root_path / fn
            if in_path.suffix.lower() not in SUPPORTED_EXTS:
                continue

            out_path = out_root / fn
            size_kb = in_path.stat().st_size // 1024

            # ===== 小于目标大小：直接复制 =====
            if size_kb <= target_kb:
                shutil.copy2(in_path, out_path)
                continue

            try:
                with Image.open(in_path) as img:
                    ext = in_path.suffix.lower()
                    print(f"🔧 压缩 {in_path}  {size_kb}KB → ≤{target_kb}KB")

                    # ===== JPG / JPEG =====
                    if ext in (".jpg", ".jpeg"):
                        if img.mode in ("RGBA", "LA"):
                            bg = Image.new("RGB", img.size, (255, 255, 255))
                            bg.paste(img, mask=img.split()[-1])
                            img = bg
                        elif img.mode != "RGB":
                            img = img.convert("RGB")

                        for q in range(95, 39, -5):
                            img.save(out_path, quality=q, optimize=True, progressive=True)
                            if out_path.stat().st_size // 1024 <= target_kb:
                                break

                    # ===== PNG =====
                    elif ext == ".png":
                        # 先无损压缩
                        for level in (9, 8, 7, 6):
                            img.save(out_path, optimize=True, compress_level=level)
                            if out_path.stat().st_size // 1024 <= target_kb:
                                break
                        else:
                            # 最后手段：调色板（轻度有损）
                            pal = img.convert("RGBA").convert(
                                "P", palette=Image.Palette.ADAPTIVE, colors=256
                            )
                            pal.save(out_path, optimize=True, compress_level=9)

                    # ===== WEBP =====
                    elif ext == ".webp":
                        img.save(out_path, lossless=True, method=6)
                        if out_path.stat().st_size // 1024 > target_kb:
                            for q in range(90, 39, -5):
                                img.save(out_path, quality=q, method=6)
                                if out_path.stat().st_size // 1024 <= target_kb:
                                    break

            except Exception as e:
                print(f"❌ 处理失败: {in_path} → {e}")

    print("✅ 图片处理完成")


def main():
    # ===== 你只需要改这里 =====
    input_dir = r"D:\TB\Products\clarks_jingya\publication\image_cutter分组图片\group_5"
    output_dir = r"D:\TB\Products\clarks_jingya\publication\image_cutter分组图片\group_5552"
    target_kb = 300

    process_one(input_dir, output_dir, target_kb)


if __name__ == "__main__":
    main()
