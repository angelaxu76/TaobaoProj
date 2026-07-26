"""
ECCO 商品图流水线 — step 2 后半步：AI 视角旋转。

前置条件：ECCO["IMAGE_CUTTER"] 下对应编码的图片已经用
image_pipeline_step2_upload_to_r2.py 上传到 R2（"ecco/" 前缀，文件名不变，
{编码}_1.jpg / {编码}_2.jpg ...）。

跟 ops/shoe_angle_ai/run_shoe_angle_rotate_urls.py / run_shoe_angle_rotate_custom.py
复用同一套 process_one_code_rotate() 底层逻辑，区别是这里"每个编码有几张图"
按 ECCO["IMAGE_CUTTER"] 本地实际文件动态探测——ECCO 各编码图片数量不固定，
不是 Clarks 那种固定 5 张，所以不用 run_batch() 的定长 shot_suffixes。

输出目录：ECCO["IMAGE_ROTATED"]，跟 IMAGE_PROCESS 是两个目录，
image_pipeline_step3_merge_and_html.py 会把两个目录的图一起合并，
不需要手动挪文件。
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from common.ai.image import GrsAIClient
from ops.shoe_angle_ai.shoe_angle_rotate import process_one_code_rotate
from ops.shoe_angle_ai.run_shoe_angle_rotate_urls import _RateLimiter, read_codes
from config import GRSAI_API_KEY, GRSAI_HOST, R2_PUBLIC_PREFIX, IMAGE_EXT, ECCO

CODE_FILE_PATH = r"D:\TB\Products\ecco\repulibcation\publication_codes.txt"

R2_SHOT_SUBDIR = "ecco"

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


def _local_suffixes_for_code(code: str) -> list[str]:
    """按 IMAGE_CUTTER 本地实际文件探测该编码有哪些编号后缀（{code}_{n}{IMAGE_EXT}）。"""
    pattern = re.compile(rf"^{re.escape(code)}_(\d+){re.escape(IMAGE_EXT)}$", re.IGNORECASE)
    nums = []
    for filename in os.listdir(ECCO["IMAGE_CUTTER"]):
        m = pattern.match(filename)
        if m:
            nums.append(int(m.group(1)))
    return [f"_{n}" for n in sorted(nums)]


def main():
    codes = read_codes(CODE_FILE_PATH)
    if not codes:
        print("未读取到任何商品编码，请检查 CODE_FILE_PATH。")
        return

    r2_prefix = f"{R2_PUBLIC_PREFIX.rstrip('/')}/{R2_SHOT_SUBDIR}"
    output_dir = str(ECCO["IMAGE_ROTATED"])
    print(f"共读取到 {len(codes)} 个商品编码: {codes}")
    print(f"输出目录: {output_dir}\n")

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    rate_lock = _RateLimiter(RATE_LIMIT_SLEEP)

    total_ok = 0
    fail_codes: list[str] = []

    def _run(code: str):
        shot_suffixes = _local_suffixes_for_code(code)
        if not shot_suffixes:
            print(f"[{code}] IMAGE_CUTTER 下未找到该编码的图片，跳过"
                  f"（是否忘了先跑 step1 / 上传 R2？）")
            return code, [], 0
        saved = process_one_code_rotate(
            code=code,
            client=client,
            r2_prefix=r2_prefix,
            output_dir=output_dir,
            shot_suffixes=shot_suffixes,
            image_ext=IMAGE_EXT,
            azimuth_deg=ROTATE_DEGREES,
            direction=ROTATE_DIRECTION,
            max_retries=MAX_RETRIES,
            retry_delay=RETRY_DELAY,
            rate_limiter=rate_lock,
            output_name_fn=_output_name,
        )
        return code, saved, len(shot_suffixes)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run, code): code for code in codes}
        for future in as_completed(futures):
            code, saved, expected = future.result()
            total_ok += len(saved)
            if len(saved) < expected:
                fail_codes.append(code)

    print(f"\n{'='*60}")
    print(f"完成: 成功 {total_ok} 张，输出目录: {output_dir}")
    if fail_codes:
        print(f"存在失败/缺失图片的商品编码: {fail_codes}")


if __name__ == "__main__":
    main()
