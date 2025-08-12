# -*- coding: utf-8 -*-
import os
import sys
import glob
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageOps

# ---------------- 裁剪核心 ----------------
def _trim_sides_numpy(img: Image.Image, tolerance: int) -> Image.Image:
    import numpy as np
    im = ImageOps.exif_transpose(img)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

    arr = np.array(im)
    h, w = arr.shape[0], arr.shape[1]
    rgb = arr[..., :3].astype("int16")

    left_ref = rgb[:, 0, :]
    right_ref = rgb[:, -1, :]

    left = 0
    for x in range(w):
        diff = (rgb[:, x, :] - left_ref)
        if (abs(diff).max(axis=1) > tolerance).any():
            left = x
            break

    right = w
    for x in range(w - 1, -1, -1):
        diff = (rgb[:, x, :] - right_ref)
        if (abs(diff).max(axis=1) > tolerance).any():
            right = x + 1
            break

    if left >= right:
        return im
    return im.crop((left, 0, right, h))

def _trim_sides_pure(img: Image.Image, tolerance: int) -> Image.Image:
    im = ImageOps.exif_transpose(img)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

    w, h = im.size
    px = im.load()

    def rgb(x, y):
        p = px[x, y]
        return p[:3] if isinstance(p, tuple) else (p, p, p)

    def same(a, b):
        return max(abs(a[0]-b[0]), abs(a[1]-b[1]), abs(a[2]-b[2])) <= tolerance

    left_refs = [rgb(0, y) for y in range(h)]
    left = 0
    for x in range(w):
        if any(not same(rgb(x, y), left_refs[y]) for y in range(h)):
            left = x
            break

    right_refs = [rgb(w - 1, y) for y in range(h)]
    right = w
    for x in range(w - 1, -1, -1):
        if any(not same(rgb(x, y), right_refs[y]) for y in range(h)):
            right = x + 1
            break

    if left >= right:
        return im
    return im.crop((left, 0, right, h))

def trim_sides(image: Image.Image, tolerance: int) -> Image.Image:
    try:
        import numpy  # noqa: F401
        return _trim_sides_numpy(image, tolerance)
    except Exception:
        return _trim_sides_pure(image, tolerance)

# -------------- 批量处理（可供 pipeline 调用） --------------
def _iter_files(input_dir: Path, patterns: List[str], recursive: bool) -> Iterable[Path]:
    if not patterns:
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]
    for pat in patterns:
        glob_pat = str(input_dir / ("**" if recursive else "") / pat)
        yield from (Path(p) for p in glob.glob(glob_pat, recursive=recursive))

def _process_one(src: Path, dst_dir: Path, tolerance: int, overwrite: bool, dry_run: bool) -> Tuple[bool, str]:
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        out = dst_dir / src.name
        if (not overwrite) and out.exists():
            return False, f"跳过（已存在）：{out}"
        if dry_run:
            return True, f"[Dry-Run] 将处理：{src} → {out}"

        with Image.open(src) as im:
            trimmed = trim_sides(im, tolerance)
            fmt = (im.format or "").upper()
            if fmt not in ("PNG", "JPEG", "JPG", "WEBP", "BMP"):
                fmt = "PNG"
            trimmed.save(out, format=fmt)
        return True, f"已裁剪保存：{out}"
    except Exception as e:
        return False, f"处理失败：{src}，原因：{e}"

def trim_sides_batch(
    input_dir: str,
    output_dir: str,
    pattern: str | None = None,     # 例："*.jpg;*.png"
    tolerance: int = 5,
    recursive: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
    workers: int = 0,
) -> dict:
    """
    供 pipeline 直接调用的入口。
    返回统计结果字典：{"total":N, "ok":A, "fail_or_skip":B, "messages":[...]}
    """
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    if not in_dir.exists() or not in_dir.is_dir():
        return {"total": 0, "ok": 0, "fail_or_skip": 0, "messages": [f"[错误] 输入目录无效：{in_dir}"]}

    patterns = [p.strip() for p in pattern.split(";")] if pattern else []
    files = list(_iter_files(in_dir, patterns, recursive))
    if not files:
        return {"total": 0, "ok": 0, "fail_or_skip": 0, "messages": ["[提示] 未找到匹配文件。"]}

    if workers and workers > 0:
        max_workers = workers
    else:
        max_workers = max(1, (os.cpu_count() or 4) - 1)

    ok = 0
    fail_or_skip = 0
    messages: List[str] = []

    if max_workers <= 1:
        for f in files:
            success, msg = _process_one(f, out_dir, tolerance, overwrite, dry_run)
            messages.append(msg)
            ok += int(success)
            fail_or_skip += int(not success)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(_process_one, f, out_dir, tolerance, overwrite, dry_run) for f in files]
            for fut in as_completed(futs):
                success, msg = fut.result()
                messages.append(msg)
                ok += int(success)
                fail_or_skip += int(not success)

    return {"total": len(files), "ok": ok, "fail_or_skip": fail_or_skip, "messages": messages}

# -------------- 可选：命令行入口（保留兼容） --------------
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

def main() -> int:
    args = _parse_args()
    res = trim_sides_batch(
        input_dir=args.input,
        output_dir=args.output,
        pattern=args.pattern,
        tolerance=args.tolerance,
        recursive=args.recursive,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        workers=args.workers,
    )
    for m in res["messages"]:
        print(m)
    print(f"\n完成：成功 {res['ok']}，失败/跳过 {res['fail_or_skip']}，共 {res['total']} 文件。")
    # 有失败但也有成功时依然返回 0，只有全失败才返回 1；输入错误你可以从消息里判断
    return 1 if (res["ok"] == 0 and res["total"] > 0) else 0

if __name__ == "__main__":
    sys.exit(main())
