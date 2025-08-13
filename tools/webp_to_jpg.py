# -*- coding: utf-8 -*-
"""
批量将 WEBP 转为 JPG（在脚本里固定目录与参数，无需命令行）
依赖：pip install pillow
"""

from __future__ import annotations
import os, glob
from pathlib import Path
from typing import List, Tuple, Dict, Iterable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps

# ========== 在这里配置 ==========
INPUT_DIR  = r"C:\Users\martin\Downloads"   # 输入目录（含 .webp）
OUTPUT_DIR = r"D:\TB\Products\barbour\document\images"    # 输出目录（生成 .jpg）
RECURSIVE  = True                        # 递归子目录
OVERWRITE  = True                        # 已存在时是否覆盖
WORKERS    = 0                           # 并发线程数；0=自动
QUALITY    = 90                          # JPEG 质量 1-95（建议 88~92）
BG         = (255, 255, 255)             # 透明像素铺底色（JPG不支持透明）
ANIMATED   = "first"                     # 'first'：动图取第一帧；'skip'：跳过动图
PRESERVE_SUBDIRS = True                  # 递归时保留原有子目录结构
# =================================

WEBP_EXTS = {".webp"}

def _iter_webp_files(input_dir: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*.webp" if recursive else "*.webp"
    for p in glob.glob(str(input_dir / pattern), recursive=recursive):
        yield Path(p)

def _ensure_rgb_flatten(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """确保输出为 RGB；如果有透明通道则铺底色"""
    im = ImageOps.exif_transpose(im)  # 处理 EXIF 方向
    if im.mode in ("RGB", "L"):
        return im.convert("RGB")
    if "A" in im.getbands() or im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        background = Image.new("RGB", rgba.size, bg)
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return im.convert("RGB")

def _save_jpeg(im_rgb, out_path, quality, exif_bytes, original_format=None):
    save_kwargs = dict(format="JPEG", quality=int(quality), optimize=True, progressive=True)
    if original_format == "JPEG":
        save_kwargs["subsampling"] = "keep"
    else:
        save_kwargs["subsampling"] = 2
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes
    im_rgb.save(out_path, **save_kwargs)


def _convert_one(
    src: Path,
    dst_root: Path,
    base_dir: Path,
    overwrite: bool,
    quality: int,
    bg: Tuple[int, int, int],
    animated: str,  # 'first' | 'skip'
    preserve_subdirs: bool,
) -> Tuple[bool, str]:
    try:
        rel = src.relative_to(base_dir) if preserve_subdirs else Path(src.name)
        out_path = (dst_root / rel).with_suffix(".jpg")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if (not overwrite) and out_path.exists():
            return False, f"跳过（已存在）：{out_path}"

        with Image.open(src) as im:
            if getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1:
                if animated == "skip":
                    return False, f"跳过（动画webp）：{src}"
                im.seek(0)  # 取第一帧

            exif_bytes = im.info.get("exif")
            rgb = _ensure_rgb_flatten(im, bg=bg)
            _save_jpeg(rgb, out_path, quality=quality, exif_bytes=exif_bytes)

        return True, f"OK：{src} → {out_path}"
    except Exception as e:
        return False, f"失败：{src} → {e}"

def convert_webp_to_jpg_batch(
    input_dir: str,
    output_dir: str,
    *,
    recursive: bool = RECURSIVE,
    overwrite: bool = OVERWRITE,
    workers: int = WORKERS,
    quality: int = QUALITY,
    bg: Tuple[int, int, int] = BG,
    animated: str = ANIMATED,
    preserve_subdirs: bool = PRESERVE_SUBDIRS,
) -> Dict[str, object]:
    """可在 pipeline 中 import 后直接调用；参数默认取顶部配置。"""
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    if not in_dir.exists() or not in_dir.is_dir():
        return {"total": 0, "ok": 0, "fail": 0, "messages": [f"[错误] 输入目录无效：{in_dir}"]}

    files = [p for p in _iter_webp_files(in_dir, recursive) if p.suffix.lower() in WEBP_EXTS]
    if not files:
        return {"total": 0, "ok": 0, "fail": 0, "messages": ["[提示] 没找到 .webp 文件"]}

    if workers <= 0:
        workers = max(1, (os.cpu_count() or 4) - 1)

    ok = fail = 0
    msgs: List[str] = []

    if workers == 1:
        for f in files:
            s, m = _convert_one(f, out_dir, in_dir, overwrite, quality, bg, animated, preserve_subdirs)
            msgs.append(m); ok += int(s); fail += int(not s)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_convert_one, f, out_dir, in_dir, overwrite, quality, bg, animated, preserve_subdirs) for f in files]
            for fut in as_completed(futs):
                s, m = fut.result()
                msgs.append(m); ok += int(s); fail += int(not s)

    return {"total": len(files), "ok": ok, "fail": fail, "messages": msgs}

def main():
    res = convert_webp_to_jpg_batch(INPUT_DIR, OUTPUT_DIR)
    for m in res["messages"]:
        print(m)
    print(f"\n完成：成功 {res['ok']} / 失败 {res['fail']} / 总计 {res['total']}")

if __name__ == "__main__":
    main()
