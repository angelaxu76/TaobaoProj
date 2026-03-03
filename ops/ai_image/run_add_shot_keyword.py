"""
批量给图片文件名插入镜头关键字。

将目录中形如 {code}_{n}.ext 的图片重命名为：
  {code}_{keyword}_{n}.ext

常用场景：
  换脸/平铺拍摄图下载后命名为 T839724E_1.webp，
  通过本脚本加上 keyword="front"，
  变为 T839724E_front_1.webp，
  即可与 run_ai_face_swap 中的 SHOT_SUFFIXES = ["_front_1"] 对齐。

支持带颜色后缀的混合编码，如 T839744F_RED_1.webp → T839744F_RED_front_1.webp。

用法：
  1. 先以 DRY_RUN = True 预览结果，确认无误后改为 False 再执行。
  2. python ops/ai_image/run_add_shot_keyword.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from helper.image.add_shot_keyword import add_shot_keyword

# ============================================================
# 运行参数（按需修改）
# ============================================================

# 待处理图片目录
INPUT_DIR  = r"D:\barbour\person"

# 输出目录（与 INPUT_DIR 相同则就地重命名；不同则复制到新目录保留原文件）
OUTPUT_DIR = INPUT_DIR

# 镜头关键字：front / flat / back / detail / ...
# 与 run_ai_face_swap.py 中 SHOT_SUFFIXES 里的关键字保持一致
KEYWORD    = "front"

# DRY_RUN = True  → 仅打印预览，不实际改动（建议先用 True 确认）
# DRY_RUN = False → 实际执行重命名/复制
DRY_RUN    = True

# ============================================================

if __name__ == "__main__":
    add_shot_keyword(INPUT_DIR, OUTPUT_DIR, KEYWORD, dry_run=DRY_RUN)
