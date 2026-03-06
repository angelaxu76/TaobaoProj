"""
reduce_image_size.py
批量压缩图片至目标文件大小，支持 JPG / PNG / WEBP，递归处理子目录。

- TARGET_PX：等比缩放到指定像素边长（正方形图片只填一个值）；0 = 不缩放
- TARGET_KB：压缩至目标文件大小；0 = 只缩放不压缩
- 两者可组合使用，先缩放再压缩
"""

import os
import shutil
from pathlib import Path
from PIL import Image

# ============================================================
# 修改这里
# ============================================================
INPUT_DIR  = r"D:\TB\Products\clarks_jingya\publication\image_cutter分组图片\group_5"
OUTPUT_DIR = r"D:\TB\Products\clarks_jingya\publication\image_cutter分组图片\group_5_compressed"
TARGET_PX   = 1500        # 输出图片的最大边长（像素）；0 = 不缩放
TARGET_KB   = 300         # 每张图片的目标大小上限（KB）；0 = 不压缩
MIN_QUALITY = 65          # JPEG 最低质量下限（低于此值电商平台可能拒绝，建议 60~75）
# ============================================================

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _compress_jpg(img: Image.Image, out_path: Path, target_kb: int, min_quality: int = 65):
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # ⚠️ 不用 progressive=True：部分电商平台（淘宝/鲸芽）只接受 baseline JPEG
    # ⚠️ 不低于 min_quality：低于 60~70 时电商平台会从 JPEG 量化表检测到并拒绝
    for q in range(95, min_quality - 1, -5):
        img.save(out_path, quality=q, optimize=True)
        if out_path.stat().st_size // 1024 <= target_kb:
            return
    # 达到质量下限仍超过目标大小时，保留当前文件（质量优先，不过度压缩）
    actual_kb = out_path.stat().st_size // 1024
    if actual_kb > target_kb:
        print(f"   ⚠️ 质量已到下限 {min_quality}，实际 {actual_kb}KB > 目标 {target_kb}KB，保留当前质量")


def _compress_png(img: Image.Image, out_path: Path, target_kb: int):
    for level in (9, 8, 7, 6):
        img.save(out_path, optimize=True, compress_level=level)
        if out_path.stat().st_size // 1024 <= target_kb:
            return
    # 最后手段：转为 JPEG（保持 RGB 质量，比调色板更安全）
    jpg_path = out_path.with_suffix(".jpg")
    rgb = img.convert("RGB")
    for q in range(85, 39, -5):
        rgb.save(jpg_path, quality=q, optimize=True)
        if jpg_path.stat().st_size // 1024 <= target_kb:
            break
    # 删除原 PNG，用 JPG 替代
    if out_path.exists():
        out_path.unlink()
    print(f"   ↳ PNG 转为 JPG: {jpg_path.name}")


def _compress_webp(img: Image.Image, out_path: Path, target_kb: int):
    img.save(out_path, lossless=True, method=6)
    if out_path.stat().st_size // 1024 <= target_kb:
        return
    for q in range(90, 39, -5):
        img.save(out_path, quality=q, method=6)
        if out_path.stat().st_size // 1024 <= target_kb:
            return


def _resize_if_needed(img: Image.Image, target_px: int) -> Image.Image:
    """等比缩放：最大边长超过 target_px 时缩放，否则原样返回。"""
    if target_px <= 0:
        return img
    max_side = max(img.size)
    if max_side <= target_px:
        return img
    ratio = target_px / max_side
    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
    return img.resize(new_size, Image.LANCZOS)


def compress_images(input_dir: str, output_dir: str, target_kb: int = 1024, target_px: int = 0):
    """
    递归处理 input_dir 下所有支持格式的图片到 output_dir。
    - target_px > 0：先等比缩放到最大边长 target_px（正方形图片即边长）
    - target_kb > 0：再压缩至目标文件大小
    - 两个条件都不触发时直接复制
    """
    src = Path(input_dir)
    dst = Path(output_dir)

    if not src.exists():
        raise FileNotFoundError(f"输入目录不存在: {src}")

    total = copied = processed = failed = 0

    for root, _, files in os.walk(src):
        root_path = Path(root)
        out_root = dst / root_path.relative_to(src)
        out_root.mkdir(parents=True, exist_ok=True)

        for fn in files:
            in_path = root_path / fn
            if in_path.suffix.lower() not in SUPPORTED_EXTS:
                continue

            out_path = out_root / fn
            size_kb = in_path.stat().st_size // 1024
            total += 1

            with Image.open(in_path) as probe:
                needs_resize = target_px > 0 and max(probe.size) > target_px
            needs_compress = target_kb > 0 and size_kb > target_kb

            if not needs_resize and not needs_compress:
                shutil.copy2(in_path, out_path)
                copied += 1
                continue

            try:
                with Image.open(in_path) as img:
                    ext = in_path.suffix.lower()
                    img = _resize_if_needed(img, target_px)

                    info = f"{in_path.name}  {img.size[0]}×{img.size[1]}px  {size_kb}KB"
                    if target_kb > 0:
                        info += f" → ≤{target_kb}KB"
                    print(f"🔧 {info}")

                    if target_kb > 0:
                        if ext in (".jpg", ".jpeg"):
                            _compress_jpg(img, out_path, target_kb, MIN_QUALITY)
                        elif ext == ".png":
                            _compress_png(img, out_path, target_kb)
                        elif ext == ".webp":
                            _compress_webp(img, out_path, target_kb)
                    else:
                        # 只缩放，直接保存（JPG 用质量 95）
                        if ext in (".jpg", ".jpeg"):
                            img.convert("RGB").save(out_path, quality=95, optimize=True)
                        else:
                            img.save(out_path)

                processed += 1
            except Exception as e:
                print(f"❌ 处理失败: {in_path} → {e}")
                failed += 1

    print(f"\n✅ 完成：共 {total} 张，直接复制 {copied}，处理 {processed}，失败 {failed}")


if __name__ == "__main__":
    compress_images(INPUT_DIR, OUTPUT_DIR, target_kb=TARGET_KB, target_px=TARGET_PX)
