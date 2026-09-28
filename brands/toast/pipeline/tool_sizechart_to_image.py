# -*- coding: utf-8 -*-
"""
TOAST 尺码表 HTML → PNG（Firefox 整页截图 + 裁掉左右纯色边）

SIZE_CHART_DIR/{编码}_size.html  →  SIZE_CHART_IMAGE_DIR/{编码}_size.png
"""
from pathlib import Path

from config import TOAST
from helper.html.html_to_png_batch import html_to_image
from helper.image.trim_sides_batch import run_cutter_pipeline


def toast_sizechart_to_image():
    html_dir = Path(TOAST["SIZE_CHART_DIR"])
    out_dir = Path(TOAST["SIZE_CHART_IMAGE_DIR"])
    raw_dir = out_dir / "_raw"   # 截图原图，裁边后输出到 out_dir

    html_to_image(str(html_dir), str(raw_dir))
    run_cutter_pipeline(str(raw_dir), str(out_dir))


if __name__ == "__main__":
    toast_sizechart_to_image()
