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
  2. 运行：python ops/shoe_angle_ai/run_shoe_angle_rotate_custom.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/shoe_angle_ai/

from run_shoe_angle_rotate_urls import run_batch

# ============================================================
# 本次运行参数（自由修改，不影响 run_shoe_angle_rotate_urls.py）
# ============================================================

# 商品编码列表：Excel（第一列为编码，可有表头行）或 txt（每行一个编码，
# 如 publication_codes.txt）。按 INPUT_FILE 扩展名自动判断，.txt 走按行读，
# 其余按 Excel 读，此时 HEADER_ROWS / CODE_COLUMN_NAME 生效。
INPUT_FILE  = r"D:\temp\publication_codes.txt"
HEADER_ROWS = 1

# 按栏目头名称定位编码列（多栏 Excel 用，不管编码在第几列都能找到；
# 读 txt 时此项不生效）。留空字符串则按原有行为，固定读第一列，不看表头文字
CODE_COLUMN_NAME = "商品编码"

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
# 输出文件名（按需修改这个函数即可，不用改 run_batch/process_one_code_rotate）
# ============================================================


def OUTPUT_NAME_FN(code: str, suffix: str, azimuth_deg: float, direction: str) -> str:
    """决定每张输出图的文件名（含扩展名）。

    默认跟 run_shoe_angle_rotate_urls.py 一样：{code}{suffix}_rotate{角度}{方向首字母}.png
    例：26185512_1_rotate15L.png

    常见改法（挑一种，把 return 换掉）：
      - 跟源图同名，直接覆盖同名文件的语义（不推荐，容易和原图混淆）：
            return f"{code}{suffix}.png"
      - 不要角度/方向信息，只加个 _ai 标记：
            return f"{code}{suffix}_ai.png"
      - 按方向单独建子文件夹风格的文件名（配合 OUTPUT_DIR 用）：
            return f"{direction.lower()}_{code}{suffix}.png"
    """
    return f"{code}_rotate{suffix}.png"


if __name__ == "__main__":
    run_batch(
        input_file=INPUT_FILE,
        header_rows=HEADER_ROWS,
        code_column_name=CODE_COLUMN_NAME,
        r2_shot_subdir=R2_SHOT_SUBDIR,
        shot_suffixes=SHOT_SUFFIXES,
        output_dir=OUTPUT_DIR,
        rotate_direction=ROTATE_DIRECTION,
        rotate_degrees=ROTATE_DEGREES,
        max_workers=MAX_WORKERS,
        max_retries=MAX_RETRIES,
        retry_delay=RETRY_DELAY,
        rate_limit_sleep=RATE_LIMIT_SLEEP,
        output_name_fn=OUTPUT_NAME_FN,
    )
