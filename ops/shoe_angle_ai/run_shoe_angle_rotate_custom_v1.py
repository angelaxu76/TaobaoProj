"""
鞋子产品图视角旋转 —— 自定义参数版 v1（提示词升级，修复"2D 拉伸伪装成旋转"）。

跟 run_shoe_angle_rotate_custom.py 是同一套底层逻辑（同一个 run_batch()
函数），唯一区别是这里显式传入 v1 提示词（shoe_angle_config_v1.py）：
  - prompt_hint_fn = build_rotate_prompt_hint_v1：正向提示词显式声明
    "这必须是真 3D 相机透视变化，不是 2D 拉伸/压缩"，并给出该方向对应的
    具体透视规律（近大远小、缝线角度重新投影）。
  - negative_prompt = SHOE_ANGLE_NEGATIVE_PROMPT_V1：把"禁止 2D 拉伸/挤压"
    相关词汇前置强化，避免被产品细节保护词汇淹没。

背景：纯侧面（90度侧拍）鞋款（比如棕色短靴）用原版提示词时，AI 容易走
捷径，直接用横向挤压/拉伸画面来应付"旋转"指令，而不是真正重绘 3D 视角。
黑色布鞋因为原图本身带斜角，AI 容易找到 3D 轴心，所以没暴露这个问题。

跟 run_shoe_angle_rotate_urls.py / run_shoe_angle_rotate_custom.py 不冲突，
改这个文件不会影响另外两个的默认行为，反过来也一样。

想跑另一批不同参数（不同 Excel / 不同 R2 目录 / 不同角度）：
  复制这个文件改个名字，改下面的参数，再运行即可，两份文件互不干扰。

用法：
  1. 改下面的参数。
  2. 运行：python ops/shoe_angle_ai/run_shoe_angle_rotate_custom_v1.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/shoe_angle_ai/

from run_shoe_angle_rotate_urls import run_batch
from shoe_angle_config_v1 import (
    SHOE_ANGLE_NEGATIVE_PROMPT_V1,
    build_rotate_prompt_hint_v1,
)

# ============================================================
# 本次运行参数（自由修改，不影响其他 run_shoe_angle_rotate_*.py）
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

# 本地输出目录（跟 custom.py 分开，避免混淆两批结果）
OUTPUT_DIR = r"D:\temp\imageOutput\ai_rotate_custom_v1"

# 旋转方向："LEFT" 或 "RIGHT"
ROTATE_DIRECTION = "LEFT"

# 旋转角度（度）—— v1 提示词已经用"真 3D 透视"描述强化了旋转指令，
# 10~15 度都可以；纯侧面鞋款建议不低于 10 度
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
    """决定每张输出图的文件名（含扩展名）。"""
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
        negative_prompt=SHOE_ANGLE_NEGATIVE_PROMPT_V1,
        prompt_hint_fn=build_rotate_prompt_hint_v1,
    )
