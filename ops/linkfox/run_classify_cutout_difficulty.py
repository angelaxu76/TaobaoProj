"""
按前景占比自动分类 barbour 详情图，把背景/留白过少、容易被抠图算法错误抠取
边缘的图片挑到 repulibcation\\1，正常图片留在 images\\detail 原地。

分类逻辑与阈值来源见 helper/image/classify_cutout_difficulty.py。

用法：
  python ops/ai_image/run_classify_cutout_difficulty.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from helper.image.classify_cutout_difficulty import split_hard_to_cut

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 待分类图片目录（新图片放这里）
INPUT_DIR = r"D:\TB\Products\barbour\images\detail"

# 难抠图图片输出目录
HARD_DIR = r"D:\TB\Products\barbour\repulibcation\1"

# 前景占比阈值，越高越严格；默认 0.65 来自已有样本统计（约 91% 准确率）
THRESHOLD = 0.65

# True=移动（INPUT_DIR 不再保留难抠图副本）；False=复制（INPUT_DIR 保留原图）
MOVE = True

# True=只打印分类结果，不实际移动/复制文件，先看看效果；确认无误后再改成 False
DRY_RUN = True

# ============================================================

if __name__ == "__main__":
    split_hard_to_cut(INPUT_DIR, HARD_DIR, threshold=THRESHOLD, move=MOVE, dry_run=DRY_RUN)
