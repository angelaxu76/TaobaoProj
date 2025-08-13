# -*- coding: utf-8 -*-
"""
将目录下的长图片裁剪成多份，每份在目标维度上 <= MAX_LEN（默认 1900）。
默认按“高度”切（适合淘宝详情长图）。这是【裁剪】不是缩放。

依赖：
    pip install pillow
"""

import os
from math import ceil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps

# ============== 可配置参数 ==============
INPUT_DIR   = Path(r"D:\TEMP\1")   # 输入目录
OUTPUT_DIR  = Path(r"D:\TEMP\2")   # 输出目录；可与输入相同
MAX_LEN     = 1900                # 每段最大长度（像素）
SPLIT_AXIS  = "height"            # "height" | "width" | "auto"
OVERLAP     = 10                  # 段与段之间重叠像素（避免切到文字），可设为 0
RECURSIVE   = False               # 是否递归处理子目录
OVERWRITE   = True                # 输出存在时是否覆盖
WORKERS     = 0                   # 线程数；0=按CPU自动
VALID_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
JPEG_QUALITY = 95                 # JPEG 保存质量

# ============== 内部实现 ==============

def _iter_images():
    if RECURSIVE:
        it = INPUT_DIR.rglob("*")
    else:
        it = INPUT_DIR.iterdir()
    for p in it:
        if p.is_file() and p.suffix.lower() in VALID_EXTS:
            yield p

def _save(img: Image.Image, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        img = img.convert("RGB")
        img.save(out_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    else:
        img.save(out_path, optimize=True)

def _slice_boxes(total: int, max_len: int, overlap: int):
    """返回一组 (start, end) 区间，确保每段长度 <= max_len，段间有 overlap 重叠（最后一段不需要）。"""
    if total <= max_len:
        return [(0, total)]

    step = max_len - max(0, overlap)  # 实际前进步幅
    if step <= 0:
        step = max_len
    boxes = []
    start = 0
    while start < total:
        end = min(start + max_len, total)
        boxes.append((start, end))
        if end >= total:
            break
        start = end - overlap  # 下一个起点回退 overlap
    return boxes

def _decide_axis(w: int, h: int, mode: str) -> str:
    mode = (mode or "height").lower()
    if mode in ("height", "width"):
        return mode
    # auto: 按较长边切
    return "height" if h >= w else "width"

def _process_one(path: Path) -> str:
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)  # 处理 EXIF 方向
            w, h = im.size
            axis = _decide_axis(w, h, SPLIT_AXIS)

            # 不需要切割：对应维度不超过 MAX_LEN
            if (axis == "height" and h <= MAX_LEN) or (axis == "width" and w <= MAX_LEN):
                # 输出到不同目录则复制；同目录且不覆盖就跳过
                out_single = (OUTPUT_DIR / path.name) if OUTPUT_DIR != INPUT_DIR else path
                if OUTPUT_DIR != INPUT_DIR:
                    _save(im, out_single)
                    return f"✅ 复制（无需切割）：{path.name} [{w}x{h}]"
                return f"✅ 无需切割：{path.name} [{w}x{h}]"

            # 需要切割
            if axis == "height":
                boxes = _slice_boxes(h, MAX_LEN, OVERLAP)
                parts = []
                for idx, (top, bottom) in enumerate(boxes, 1):
                    box = (0, top, w, bottom)
                    crop = im.crop(box)
                    out_name = f"{path.stem}_p{idx:02d}{path.suffix.lower()}"
                    out_path = OUTPUT_DIR / out_name
                    if not OVERWRITE and out_path.exists():
                        parts.append(out_name + " (skip)")
                        continue
                    _save(crop, out_path)
                    parts.append(out_name)
                return f"✂️ 高度切割：{path.name} -> {len(parts)} 段（{', '.join(parts)}）"

            else:  # width
                boxes = _slice_boxes(w, MAX_LEN, OVERLAP)
                parts = []
                for idx, (left, right) in enumerate(boxes, 1):
                    box = (left, 0, right, h)
                    crop = im.crop(box)
                    out_name = f"{path.stem}_p{idx:02d}{path.suffix.lower()}"
                    out_path = OUTPUT_DIR / out_name
                    if not OVERWRITE and out_path.exists():
                        parts.append(out_name + " (skip)")
                        continue
                    _save(crop, out_path)
                    parts.append(out_name)
                return f"✂️ 宽度切割：{path.name} -> {len(parts)} 段（{', '.join(parts)}）"

    except Exception as e:
        return f"❌ 失败：{path.name} ({e})"

def main():
    assert INPUT_DIR.exists(), f"输入目录不存在：{INPUT_DIR}"
    if OUTPUT_DIR != INPUT_DIR:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = list(_iter_images())
    if not files:
        print(f"未在 {INPUT_DIR} 找到图片（{', '.join(sorted(VALID_EXTS))}）")
        return

    workers = (os.cpu_count() or 4) if WORKERS in (0, None) else WORKERS
    print(f"开始处理：{len(files)} 张，轴={SPLIT_AXIS}，阈值≤{MAX_LEN}，重叠={OVERLAP}，线程={workers}")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_process_one, p) for p in files]
        for f in as_completed(futs):
            print(f.result())
    print("全部完成。")

if __name__ == "__main__":
    main()
