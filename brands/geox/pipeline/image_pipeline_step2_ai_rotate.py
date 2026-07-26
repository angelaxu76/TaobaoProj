"""
GEOX 商品图流水线 — step 2 后半步：AI 视角旋转。

前置条件：GEOX["IMAGE_CUTTER"] 下对应编码的图片已经用
image_pipeline_step2_upload_to_r2.py 上传到 R2（"geox/" 前缀，文件名不变，
{编码}_1.jpg ~ {编码}_6.jpg —— step1 末尾已把原始的 00/10/30/50/60/40 数字
后缀改成了固定顺序的编号：0->1, 10->2, 30->3, 50->4, 60->5, 40->6）。

GEOX 每款商品固定是这 6 张图，跟 Camper 一样直接复用
ops/shoe_angle_ai/run_shoe_angle_rotate_urls.py 的 run_batch()，用法跟
run_shoe_angle_rotate_custom.py 一样 —— 想跑不同参数就复制这个文件改参数，
不用改 run_batch() 本身。

输出目录：GEOX["IMAGE_ROTATED"]，跟 IMAGE_CUTTER 是两个目录，
image_pipeline_step3_merge_and_html.py 会把两个目录的图一起合并，
不需要手动挪文件。
"""
from ops.shoe_angle_ai.run_shoe_angle_rotate_urls import run_batch
from ops.shoe_angle_ai.shoe_angle_config_v1 import (
    SHOE_ANGLE_NEGATIVE_PROMPT_V1,
    build_rotate_prompt_hint_v1,
)
from config import GEOX

INPUT_FILE = r"D:\TB\Products\geox\repulibcation\publication_codes.txt"
HEADER_ROWS = 1
CODE_COLUMN_NAME = ""

R2_SHOT_SUBDIR = "geox"
SHOT_SUFFIXES = ["_1", "_2", "_3", "_4", "_5", "_6"]

OUTPUT_DIR = str(GEOX["IMAGE_ROTATED"])

ROTATE_DIRECTION = "LEFT"
ROTATE_DEGREES = 15

MAX_WORKERS = 3
MAX_RETRIES = 2
RETRY_DELAY = 8.0
RATE_LIMIT_SLEEP = 2.0


def _output_name(code: str, suffix: str, azimuth_deg: float, direction: str) -> str:
    # batch_merge_images（step3）只认 .jpg 后缀，这里存成 .jpg 而不是默认的 .png，
    # 不然 AI 旋转出来的图会被 step3 的合并步骤直接忽略。
    return f"{code}{suffix}_rotate{azimuth_deg:g}{direction.upper()[0]}.jpg"


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
        output_name_fn=_output_name,
        negative_prompt=SHOE_ANGLE_NEGATIVE_PROMPT_V1,
        prompt_hint_fn=build_rotate_prompt_hint_v1,
    )
