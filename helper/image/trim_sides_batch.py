# -*- coding: utf-8 -*-
"""
裁剪图片左右两侧的纯色边缘（更稳健版本，API 兼容）。
保留对外函数：
- trim_sides(image: PIL.Image.Image, tolerance: int) -> PIL.Image.Image
- trim_sides_batch(input_path: Path, output_path: Path, options: Optional[Dict[str, Any]] = None) -> dict
"""

from __future__ import annotations

import os
import glob
from pathlib import Path
from typing import Iterable, List, Tuple, Optional, Dict, Any

from PIL import Image, ImageOps, ImageFile

# ----------- 常见大图/截断图容错 -----------
# 允许载入被截断的图，避免 "image file is truncated" 报错
ImageFile.LOAD_TRUNCATED_IMAGES = True
# 如需避开 DecompressionBomb 警告，可解除注释下一行（自行权衡）
# Image.MAX_IMAGE_PIXELS = None

# 可选加速：有 numpy 则用矢量化，否则走纯 Python
try:
    import numpy as _np  # noqa: F401
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False


# =================== 裁剪核心 ===================

def _prepare_image(img: Image.Image) -> Image.Image:
    """统一处理：应用 EXIF 方向，转为 RGB/RGBA，保证可索引。"""
    im = ImageOps.exif_transpose(img)
    # 优先保留透明通道，便于精确对边
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    return im


def _trim_sides_numpy(img: Image.Image, tolerance: int) -> Image.Image:
    im = _prepare_image(img)
    import numpy as np  # 局部导入，确保 _HAS_NUMPY 为真时可用
    arr = np.array(im)

    h, w = arr.shape[0], arr.shape[1]
    rgb = arr[..., :3].astype("int16")

    # 参考列：最左、最右
    left_ref = rgb[:, 0, :]
    right_ref = rgb[:, -1, :]

    left = 0
    for x in range(w):
        diff = rgb[:, x, :] - left_ref
        # 任意一行超出容差，就认为不是纯边框
        if (abs(diff).max(axis=1) > tolerance).any():
            left = x
            break

    right = w
    for x in range(w - 1, -1, -1):
        diff = rgb[:, x, :] - right_ref
        if (abs(diff).max(axis=1) > tolerance).any():
            right = x + 1
            break

    if left >= right:
        return im
    return im.crop((left, 0, right, h))


def _trim_sides_pure(img: Image.Image, tolerance: int) -> Image.Image:
    im = _prepare_image(img)
    w, h = im.size
    px = im.load()

    def rgb(x: int, y: int):
        p = px[x, y]
        # p 可能是 int/tuple
        if isinstance(p, tuple):
            return p[:3]
        return (p, p, p)

    def close(a, b) -> bool:
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) <= tolerance

    left_refs = [rgb(0, y) for y in range(h)]
    left = 0
    for x in range(w):
        # 这一列与最左列任一点差异超过容差 => 非纯边
        if any(not close(rgb(x, y), left_refs[y]) for y in range(h)):
            left = x
            break

    right_refs = [rgb(w - 1, y) for y in range(h)]
    right = w
    for x in range(w - 1, -1, -1):
        if any(not close(rgb(x, y), right_refs[y]) for y in range(h)):
            right = x + 1
            break

    if left >= right:
        return im
    return im.crop((left, 0, right, h))


def trim_sides(image: Image.Image, tolerance: int) -> Image.Image:
    """
    裁剪单张图片左右两侧纯色边框，tolerance 为颜色差容忍度。
    若安装了 numpy，则走矢量化实现；否则使用纯 Python 实现。
    """
    if _HAS_NUMPY:
        try:
            return _trim_sides_numpy(image, tolerance)
        except Exception:
            # numpy 存在但底层 DLL 问题时的兜底
            return _trim_sides_pure(image, tolerance)
    else:
        return _trim_sides_pure(image, tolerance)


# =================== 批量处理 ===================

def _iter_files(input_dir: Path, patterns: List[str], recursive: bool) -> Iterable[Path]:
    if not patterns:
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]
    for pat in patterns:
        glob_pat = str(input_dir / ("**" if recursive else "") / pat)
        yield from (Path(p) for p in glob.glob(glob_pat, recursive=recursive))


def _choose_save_format(src_format: str, mode: str) -> str:
    """
    选择输出格式，并对 JPEG 做模式纠偏（RGBA/LA 不能直接存 JPEG）。
    规则：
    - 优先沿用原格式（若是常见格式）
    - 不在支持列表 => 使用 PNG
    """
    fmt = (src_format or "").upper()
    allowed = {"PNG", "JPEG", "JPG", "WEBP", "BMP"}
    if fmt not in allowed:
        return "PNG"
    if fmt in {"JPEG", "JPG"} and mode not in {"L", "LA", "RGB"}:
        # 有 alpha 或其它特殊模式时，改用 PNG 更稳
        return "PNG"
    return "JPEG" if fmt == "JPG" else fmt


def _safe_save(img: Image.Image, out_path: Path, src_format: str):
    fmt = _choose_save_format(src_format, img.mode)

    # 如果最终是 JPEG，统一转 RGB，避免 “cannot write mode RGBA as JPEG”
    save_img = img
    if fmt in {"JPEG", "JPG"} and img.mode not in {"L", "RGB"}:
        save_img = img.convert("RGB")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_img.save(out_path, format=fmt)


def _process_one(
    src: Path,
    dst_dir: Path,
    tolerance: int,
    overwrite: bool,
    dry_run: bool
) -> Tuple[bool, str]:
    try:
        out = dst_dir / src.name
        if (not overwrite) and out.exists():
            return False, f"跳过（已存在）：{out}"
        if dry_run:
            return True, f"[Dry-Run] 将处理：{src} → {out}"

        with Image.open(src) as im:
            trimmed = trim_sides(im, tolerance)
            _safe_save(trimmed, out, im.format or "")

        return True, f"已裁剪保存：{out}"
    except Exception as e:
        return False, f"处理失败：{src}，原因：{e}"


def trim_sides_batch(
    input_path: Optional[Any] = None,
    output_path: Optional[Any] = None,
    options: Optional[Dict[str, Any]] = None,
    **kwargs
) -> dict:
    """
    供 pipeline 调用的批量裁剪入口。

    参数支持多种形式（为了和项目其他代码风格统一）：
        1）位置参数：
            trim_sides_batch("D:/in", "D:/out", {...})
        2）关键词参数（兼容你常用的命名）：
            trim_sides_batch(input_dir="D:/in", output_dir="D:/out", options={...})
        3）Path 对象：
            trim_sides_batch(Path("D:/in"), Path("D:/out"))

    options 可选字段：
        pattern     - 文件匹配模式（如 "*.jpg;*.png"），默认常见图片格式
        tolerance   - 容差（默认 5）
        recursive   - 是否递归子目录（默认 False）
        overwrite   - 是否覆盖已有文件（默认 False）
        dry_run     - 仅测试不写入（默认 False）
        workers     - 并行线程数（默认 CPU核数-1，至少 1）
    """
    # 兼容 input_dir / output_dir 这种命名
    if input_path is None:
        input_path = kwargs.get("input_dir")
    if output_path is None:
        output_path = kwargs.get("output_dir")

    if input_path is None or output_path is None:
        raise ValueError("必须提供 input_path/output_path 或 input_dir/output_dir")

    # 接受 str / Path，统一转成 Path
    input_path = Path(input_path)
    output_path = Path(output_path)

    # 默认参数
    opts = {
        "pattern": "*.jpg;*.jpeg;*.png;*.webp;*.bmp",
        "tolerance": 5,
        "recursive": False,
        "overwrite": False,
        "dry_run": False,
        "workers": max(1, (os.cpu_count() or 4) - 1),
    }
    if options:
        opts.update(options or {})

    if not input_path.exists() or not input_path.is_dir():
        return {
            "total": 0,
            "ok": 0,
            "fail_or_skip": 0,
            "messages": [f"[错误] 输入目录无效：{input_path}"],
        }

    patterns = [p.strip() for p in (opts["pattern"] or "").split(";") if p.strip()]
    files = list(_iter_files(input_path, patterns, opts["recursive"]))
    if not files:
        return {
            "total": 0,
            "ok": 0,
            "fail_or_skip": 0,
            "messages": ["[提示] 未找到匹配文件。"],
        }

    ok = 0
    fail_or_skip = 0
    messages: List[str] = []

    output_path.mkdir(parents=True, exist_ok=True)

    workers = int(opts.get("workers", 1) or 1)
    if workers <= 1:
        # 单线程
        for f in files:
            success, msg = _process_one(
                f, output_path, opts["tolerance"], opts["overwrite"], opts["dry_run"]
            )
            messages.append(msg)
            ok += int(success)
            fail_or_skip += int(not success)
    else:
        # 多线程
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [
                ex.submit(
                    _process_one,
                    f,
                    output_path,
                    opts["tolerance"],
                    opts["overwrite"],
                    opts["dry_run"],
                )
                for f in files
            ]
            for fut in as_completed(futures):
                success, msg = fut.result()
                messages.append(msg)
                ok += int(success)
                fail_or_skip += int(not success)

    return {"total": len(files), "ok": ok, "fail_or_skip": fail_or_skip, "messages": messages}



# =================== 命令行入口（保留兼容） ===================

def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="裁剪图片左右纯色边缘（支持 pipeline 导入调用）")
    p.add_argument("--input", "-i", required=True)
    p.add_argument("--output", "-o", required=True)
    p.add_argument("--pattern", "-p", default=None, help='如："*.jpg;*.png"')
    p.add_argument("--tolerance", "-t", type=int, default=5)
    p.add_argument("--recursive", "-r", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--workers", type=int, default=0)
    return p.parse_args()

from pathlib import Path
import os

def run_cutter_pipeline(input_dir: str, output_dir: str):
    """
    一键执行图片边缘裁剪的 Pipeline 封装。

    参数:
        input_dir  : 输入图片文件夹路径
        output_dir : 裁剪后图片输出路径
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    options = {
        "pattern": "*.jpg;*.jpeg;*.png;*.webp;*.bmp",
        "tolerance": 5,
        "recursive": False,
        "overwrite": True,
        "dry_run": False,
        "workers": max(1, (os.cpu_count() or 4) - 1),
    }

    print(f"[Cutter] 正在处理图片：{input_path} -> {output_path}")
    result = trim_sides_batch(input_path, output_path, options)
    print(f"[Cutter] 完成，结果: {result}")
    return result


if __name__ == "__main__":
    # ===== 这里直接定义输入/输出目录 =====
    DEFAULT_INPUT = Path(r"D:\TB\HTMLToImage\output")   # 修改成你的输入目录
    DEFAULT_OUTPUT = Path(r"D:\TB\HTMLToImage\cutter") # 修改成你的输出目录

    # 默认参数（可根据需要修改）
    opts = {
        "pattern": "*.jpg;*.jpeg;*.png;*.webp;*.bmp",
        "tolerance": 5,
        "recursive": False,
        "overwrite": True,
        "dry_run": False,
        "workers": max(1, (os.cpu_count() or 4) - 1),
    }

    print(f"▶ 默认运行: {DEFAULT_INPUT} → {DEFAULT_OUTPUT}")
    res = trim_sides_batch(DEFAULT_INPUT, DEFAULT_OUTPUT, opts)
    print(res)


