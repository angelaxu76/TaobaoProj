
# -*- coding: utf-8 -*-
"""
TOAST 尺码表 HTML → PNG（Firefox 整页截图 + 裁掉左右纯色边）

SIZE_CHART_DIR/{编码}_size.html  →  SIZE_CHART_IMAGE_DIR/{编码}_size.png

- 默认只转还没有 png 的 html（尺码表长期保留在 document/ 下，不必每次全部重截）
- 传 codes_file 时只转这些编码
"""
import re
import shutil
from pathlib import Path
from typing import Optional

from config import TOAST
from helper.html.html_to_png_batch import html_to_image
from helper.image.trim_sides_batch import run_cutter_pipeline


def toast_sizechart_to_image(codes_file: Optional[Path] = None, overwrite: bool = False):
    html_dir = Path(TOAST["SIZE_CHART_DIR"])
    out_dir = Path(TOAST["SIZE_CHART_IMAGE_DIR"])
    raw_dir = out_dir / "_raw"   # 截图原图，裁边后输出到 out_dir
    todo_dir = out_dir / "_todo_html"   # 本次待转的 html（截图脚本按整个目录处理）

    html_files = sorted(html_dir.glob("*_size.html"))
    if codes_file:
        with open(codes_file, "r", encoding="utf-8") as f:
            codes = {re.sub(r"\s+", "", c).upper() for c in f if c.strip()}
        html_files = [p for p in html_files if p.name[: -len("_size.html")].upper() in codes]
    if not overwrite:
        html_files = [p for p in html_files if not (out_dir / f"{p.stem}.png").exists()]

    if not html_files:
        print("⏭️ 没有需要转换的尺码表 html")
        return

    shutil.rmtree(todo_dir, ignore_errors=True)
    shutil.rmtree(raw_dir, ignore_errors=True)
    todo_dir.mkdir(parents=True, exist_ok=True)
    for p in html_files:
        shutil.copy2(p, todo_dir / p.name)
    print(f"📦 待转尺码表 {len(html_files)} 个 → {out_dir}")

    html_to_image(str(todo_dir), str(raw_dir))
    run_cutter_pipeline(str(raw_dir), str(out_dir))
    shutil.rmtree(todo_dir, ignore_errors=True)


if __name__ == "__main__":
    toast_sizechart_to_image()
