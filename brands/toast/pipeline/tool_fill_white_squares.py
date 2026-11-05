# -*- coding: utf-8 -*-
"""
TOAST 用白底图补齐被手动删除的 LaMa 错图

用法：在 IMAGE_CUTTER 里手动删掉 LaMa 补错的图，然后运行本脚本：
  python -m brands.toast.pipeline.tool_fill_white_squares

- 只补 IMAGE_CUTTER 里缺少的文件，已有的图一律不动
- 补上的图同时覆盖 IMAGE_DIR（document 图库）里的同名错图，不用再跑 RUN_4_COPY_DOC
"""
import shutil
from pathlib import Path
from typing import List

from config import TOAST


def toast_fill_white_squares() -> List[str]:
    cutter_dir = Path(TOAST["IMAGE_CUTTER"])
    white_dir = Path(TOAST["IMAGE_CUTTER_WHITE"])
    doc_dir = Path(TOAST["IMAGE_DIR"])

    white_files = sorted(white_dir.glob("*.jpg"))
    if not white_files:
        print(f"⚠️ 白底图目录没有图片：{white_dir}")
        return []

    # LaMa 目录为空多半是还没生成或被清空，不是手动删图，全补成白底就错了
    if not any(cutter_dir.glob("*.jpg")):
        print(f"⚠️ LaMa 图片目录没有图片，已停止：{cutter_dir}")
        return []

    doc_dir.mkdir(parents=True, exist_ok=True)
    filled: List[str] = []
    for src in white_files:
        target = cutter_dir / src.name
        if target.exists():
            continue
        shutil.copyfile(src, target)
        shutil.copyfile(src, doc_dir / src.name)
        filled.append(src.name)
        print(f"✅ 已补：{src.name}")

    print(f"🎯 共补 {len(filled)} 张，LaMa 目录原有的 {len(white_files) - len(filled)} 张未改动")
    return filled


if __name__ == "__main__":
    toast_fill_white_squares()
