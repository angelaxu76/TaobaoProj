"""
鞋子产品图视角旋转 —— 自定义参数版（不影响 run_shoe_angle_rotate_urls.py）。

跟 run_shoe_angle_rotate_urls.py 是同一套底层逻辑（同一个 run_batch()
函数），区别只是这里的"本次运行参数"是独立的一份，改这个文件不会影响
run_shoe_angle_rotate_urls.py 直接运行时的默认行为，反过来也一样。

想跑另一批不同参数（不同 Excel / 不同 R2 目录 / 不同角度）：
  复制这个文件改个名字（比如 run_shoe_angle_rotate_custom_geox.py），
  改下面的参数，再运行即可，两份文件互不干扰。

用法：
  1. 改下面的参数。
  2. 运行：python ops/ai_image/run_shoe_angle_rotate_custom.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/ai_image/

from run_shoe_angle_rotate_urls import run_batch

# ============================================================
# 本次运行参数（自由修改，不影响 run_shoe_angle_rotate_urls.py）
# ============================================================

# 商品编码列表 Excel（第一列为编码，可有表头行）
INPUT_FILE  = r"D:\shoes_angle\codes.xlsx"
HEADER_ROWS = 1

# 图片所在 R2 子目录（"" 表示根目录直接拼 code，不加子目录）
R2_SHOT_SUBDIR = "clarks"

# 每款商品的图片后缀
SHOT_SUFFIXES = [f"_{i}" for i in range(1, 6)]

# 本地输出目录
OUTPUT_DIR = r"D:\temp\imageOutput\ai_rotate_custom"

# 旋转方向："LEFT" 或 "RIGHT"
ROTATE_DIRECTION = "LEFT"

# 旋转角度（度）
ROTATE_DEGREES = 15

# 并发线程数
MAX_WORKERS = 10

# 每张图最大重试次数（不含首次）
MAX_RETRIES = 2
RETRY_DELAY = 8.0

# 限速：每次提交 API 任务后最少间隔秒数
RATE_LIMIT_SLEEP = 2.0

# ============================================================


if __name__ == "__main__":
    run_batch(
        input_file=INPUT_FILE,
        header_rows=HEADER_ROWS,
        r2_shot_subdir=R2_SHOT_SUBDIR,
        shot_suffixes=SHOT_SUFFIXES,
        output_dir=OUTPUT_DIR,
        rotate_direction=ROTATE_DIRECTION,
        rotate_degrees=ROTATE_DEGREES,
        max_workers=MAX_WORKERS,
        max_retries=MAX_RETRIES,
        retry_delay=RETRY_DELAY,
        rate_limit_sleep=RATE_LIMIT_SLEEP,
    )
