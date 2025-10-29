# -*- coding: utf-8 -*-
"""
将目录下的长图片裁剪成多份，每份在目标维度上 <= max_len（默认 1900）。
默认按“高度”切（适合淘宝详情长图）。这是【裁剪】不是缩放。

依赖：
    pip install pillow
"""

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from PIL import Image, ImageOps

VALID_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
JPEG_QUALITY = 95

def _iter_images(input_dir: Path, recursive: bool) -> Iterable[Path]:
    """遍历目录下的图片文件"""
    it = input_dir.rglob("*") if recursive else input_dir.iterdir()
    for p in it:
        if p.is_file() and p.suffix.lower() in VALID_EXTS:
            yield p

def _save(img: Image.Image, out_path: Path):
    """保存图片（JPEG 转 RGB 并设质量）"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        img = img.convert("RGB")
        img.save(out_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    else:
        img.save(out_path, optimize=True)

def _slice_boxes(total: int, max_len: int, overlap: int):
    """计算切割区间"""
    if total <= max_len:
        return [(0, total)]
    step = max_len - max(0, overlap)
    if step <= 0:
        step = max_len
    boxes = []
    start = 0
    while start < total:
        end = min(start + max_len, total)
        boxes.append((start, end))
        if end >= total:
            break
        start = end - overlap
    return boxes

def _decide_axis(w: int, h: int, mode: str) -> str:
    """决定切割轴"""
    mode = (mode or "height").lower()
    if mode in ("height", "width"):
        return mode
    return "height" if h >= w else "width"

def _process_one(
    path: Path,
    output_dir: Path,
    max_len: int,
    split_axis: str,
    overlap: int,
    overwrite: bool
) -> str:
    """处理单张图片"""
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)  # 按 EXIF 修正方向
            w, h = im.size
            axis = _decide_axis(w, h, split_axis)

            # 不需要切割
            if (axis == "height" and h <= max_len) or (axis == "width" and w <= max_len):
                out_single = (output_dir / path.name) if output_dir != path.parent else path
                if output_dir != path.parent:
                    _save(im, out_single)
                    return f"✅ 复制（无需切割）：{out_single}"
                return f"✅ 无需切割：{path} [{w}x{h}]"

            parts = []
            if axis == "height":
                boxes = _slice_boxes(h, max_len, overlap)
                for idx, (top, bottom) in enumerate(boxes, 1):
                    crop = im.crop((0, top, w, bottom))
                    out_name = f"{path.stem}_p{idx:02d}{path.suffix.lower()}"
                    out_path = output_dir / out_name
                    if not overwrite and out_path.exists():
                        parts.append(out_name + " (skip)")
                        continue
                    _save(crop, out_path)
                    parts.append(out_name)
                return f"✂️ 高度切割：{path.name} -> {len(parts)} 段（{', '.join(parts)}）"
            else:
                boxes = _slice_boxes(w, max_len, overlap)
                for idx, (left, right) in enumerate(boxes, 1):
                    crop = im.crop((left, 0, right, h))
                    out_name = f"{path.stem}_p{idx:02d}{path.suffix.lower()}"
                    out_path = output_dir / out_name
                    if not overwrite and out_path.exists():
                        parts.append(out_name + " (skip)")
                        continue
                    _save(crop, out_path)
                    parts.append(out_name)
                return f"✂️ 宽度切割：{path.name} -> {len(parts)} 段（{', '.join(parts)}）"
    except Exception as e:
        return f"❌ 失败：{path.name} ({e})"

def split_image_by_size(
    input_dir: Path,
    output_dir: Path,
    max_len: int = 1900,
    split_axis: str = "height",
    overlap: int = 10,
    recursive: bool = False,
    overwrite: bool = True,
    workers: int = 0
):
    """批量切割入口"""
    assert input_dir.exists(), f"输入目录不存在：{input_dir}"
    if output_dir != input_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    files = list(_iter_images(input_dir, recursive))
    if not files:
        print(f"未在 {input_dir} 找到图片（{', '.join(sorted(VALID_EXTS))}）")
        return

    if workers <= 0:
        workers = max(1, (os.cpu_count() or 4) - 1)

    print(f"开始处理：{len(files)} 张，轴={split_axis}，阈值≤{max_len}，重叠={overlap}，线程={workers}")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_process_one, p, output_dir, max_len, split_axis, overlap, overwrite) for p in files]
        for f in as_completed(futs):
            print(f.result())
    print("全部完成。")

if __name__ == "__main__":
    # 示例调用
    split_image_by_size(
        input_dir=Path(r"D:\TB\HTMLToImage\output"),
        output_dir=Path(r"D:\TB\HTMLToImage\output_split"),
        max_len=1900
    )
