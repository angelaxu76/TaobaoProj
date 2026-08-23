"""
图片批量重命名脚本。

重命名规则：{code}_{keyword}_{n}.jpg
详细逻辑见 helper/image/rename_images.py

运行：python ops/run_rename_images.py
"""
import os
import sys

from sqlalchemy import False_

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helper.image.add_shot_keyword import add_shot_keyword

# ============================================================
# 运行参数（按需修改）
# ============================================================

INPUT_DIR  = r"D:\TB\Products\barbour\repulibcation\classify\person"
OUTPUT_DIR = INPUT_DIR          # 与 INPUT_DIR 相同则就地重命名
KEYWORD    = "front"            # front / flat / detail / ...
DRY_RUN    = False               # True = 仅预览；False = 实际执行

# ============================================================

if __name__ == "__main__":
    add_shot_keyword(INPUT_DIR, OUTPUT_DIR, KEYWORD, dry_run=DRY_RUN)
