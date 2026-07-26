"""
批量鞋子产品图视角旋转脚本（按商品编码 + R2 已上传图）。

原理：跟 legacy/run_shoe_angle_gen.py 一致，用 GrsAI nano-banana-2 图生图模型
      对已上传到 R2 的鞋子图片做统一角度旋转，img_1/img_2 都传同一张原图
      （强化细节保留），产品细节（logo/材质/颜色/走线/鞋底）由负向提示词锁定
      不允许改变。

跟 legacy/run_shoe_angle_gen.py 的区别：
  - 输入是 Excel 商品编码列表 + R2 已上传图，不需要本地图 + 上传步骤
  - 每款固定处理 SHOT_SUFFIXES 张图（默认 5 张：_1 ~ _5），只生成 1 个角度，
    不是每款 3 个角度变体

用法（直接运行本文件，用下面"本次运行参数"这组默认值）：
  1. 在 INPUT_FILE 指定的 Excel 第一列填入商品编码（可有表头行）。
  2. 确认 R2 上对应图片路径是
     {R2_PUBLIC_PREFIX}/{R2_SHOT_SUBDIR}/{商品编码}{后缀}{IMAGE_EXT}
     例：.../clarks/26185512_1.jpg ~ 26185512_5.jpg
  3. 按需调整 ROTATE_DIRECTION / ROTATE_DEGREES。
  4. 运行：python ops/shoe_angle_ai/run_shoe_angle_rotate_urls.py

想用一套不同的参数跑（比如不同 Excel、不同角度），不要直接改这个文件——
复制 run_shoe_angle_rotate_custom.py 改名改参数，import 这里的 run_batch() 就行，
两边互不影响。run_batch() 就是这份脚本对外暴露的"pipeline 入口"。

输出文件命名：{商品编码}{后缀}_rotate{角度}{方向首字母}.png
  例：26185512_1_rotate10L.png

本功能专用配置（模型、负向提示词、R2写入凭证）在同文件夹的
shoe_angle_config.py 修改；业务逻辑在同文件夹的 shoe_angle_rotate.py。
GRSAI_API_KEY / GRSAI_HOST / R2_PUBLIC_PREFIX / IMAGE_EXT 是多条 AI 流水线
共用的全局配置，仍在 cfg/ai_config.py，从 config.py 导入。
"""
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root

import openpyxl
from common.ai.image import GrsAIClient
from ops.shoe_angle_ai.shoe_angle_rotate import process_one_code_rotate
from config import GRSAI_API_KEY, GRSAI_HOST, R2_PUBLIC_PREFIX, IMAGE_EXT

# ============================================================
# 本次运行参数（直接运行本文件时用这组值；想换参数请用
# run_shoe_angle_rotate_custom.py，不要改这里）
# ============================================================

# 商品编码列表 Excel（第一列为编码，可有表头行）
INPUT_FILE  = r"D:\shoes_angle\codes.xlsx"
HEADER_ROWS = 1

# 图片所在 R2 子目录（"" 表示根目录直接拼 code，不加子目录）
R2_SHOT_SUBDIR = "clarks"

# 每款商品的图片后缀（5张：{code}_1 ~ {code}_5）
SHOT_SUFFIXES = [f"_{i}" for i in range(1, 6)]

# 本地输出目录（平铺，不分子文件夹）
OUTPUT_DIR = r"D:\temp\imageOutput\ai_rotate10"

# 旋转方向："LEFT" 或 "RIGHT"，统一应用到所有图片
ROTATE_DIRECTION = "LEFT"

# 旋转角度（度）
ROTATE_DEGREES = 10

# 并发线程数（这里指"同时处理几个商品编码"，每个编码内部 5 张图是顺序调用；
# 建议 2~3，过高容易触发 API 限流）
MAX_WORKERS = 2

# 每张图最大重试次数（不含首次）
MAX_RETRIES = 2
RETRY_DELAY = 8.0

# 限速：每次提交 API 任务后最少间隔秒数（跨所有并发线程共享）
RATE_LIMIT_SLEEP = 2.0

# ============================================================
# Pipeline 入口（给 run_shoe_angle_rotate_custom.py 之类的脚本 import 用）
# ============================================================


class _RateLimiter:
    """每次 acquire() 之间至少间隔 min_interval 秒（线程安全）。"""

    def __init__(self, min_interval: float) -> None:
        self._lock = threading.Lock()
        self._last_time = 0.0
        self._min_interval = min_interval

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delta = self._min_interval - (now - self._last_time)
            if delta > 0:
                time.sleep(delta)
            self._last_time = time.monotonic()


def read_codes_from_excel(path: str, header_rows: int = 1) -> list[str]:
    """从 Excel 第一列读取商品编码列表。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    codes = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < header_rows:
            continue
        val = row[0] if row else None
        if val is not None and str(val).strip():
            codes.append(str(val).strip())
    wb.close()
    return codes


def run_batch(
    *,
    input_file: str,
    header_rows: int = 1,
    r2_shot_subdir: str,
    shot_suffixes: list[str],
    output_dir: str,
    rotate_direction: str = "LEFT",
    rotate_degrees: float = 10.0,
    max_workers: int = 2,
    max_retries: int = 2,
    retry_delay: float = 8.0,
    rate_limit_sleep: float = 2.0,
    output_name_fn=None,
) -> None:
    """批量视角旋转的完整流程：读 Excel 编码 → 拼 R2 URL → 并发生成 → 汇总。

    所有参数都是显式传入，不依赖本文件顶部的模块级常量——这样其他脚本可以
    用一套完全不同的参数调用这个函数，不会跟直接运行本文件的默认配置互相
    影响。想跑一套自定义参数，写一个新脚本调用这个函数就行，参考
    run_shoe_angle_rotate_custom.py。

    output_name_fn: 可选，自定义输出文件名，签名
                     (code, suffix, azimuth_deg, direction) -> str（含扩展名）。
                     不传时用默认命名 "{code}{suffix}_rotate{角度}{方向首字母}.png"。
    """
    codes = read_codes_from_excel(input_file, header_rows)
    if not codes:
        print("未读取到任何商品编码，请检查 input_file 和 header_rows。")
        return

    direction_cn = "左" if rotate_direction.upper() == "LEFT" else "右"
    print(f"共读取到 {len(codes)} 个商品编码: {codes}")
    print(f"每款处理图片后缀: {shot_suffixes}  → 共 {len(codes) * len(shot_suffixes)} 张")
    print(f"统一{direction_cn}转 {rotate_degrees:g}°")
    print(f"输出目录: {output_dir}\n")

    r2_prefix = f"{R2_PUBLIC_PREFIX.rstrip('/')}/{r2_shot_subdir}" if r2_shot_subdir else R2_PUBLIC_PREFIX

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    rate_lock = _RateLimiter(rate_limit_sleep)

    total_ok = 0
    fail_codes: list[str] = []

    def _run(code: str) -> tuple[str, list[str]]:
        saved = process_one_code_rotate(
            code=code,
            client=client,
            r2_prefix=r2_prefix,
            output_dir=output_dir,
            shot_suffixes=shot_suffixes,
            image_ext=IMAGE_EXT,
            azimuth_deg=rotate_degrees,
            direction=rotate_direction,
            max_retries=max_retries,
            retry_delay=retry_delay,
            rate_limiter=rate_lock,
            output_name_fn=output_name_fn,
        )
        return code, saved

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run, code): code for code in codes}
        for future in as_completed(futures):
            code, saved = future.result()
            if saved:
                total_ok += len(saved)
            if len(saved) < len(shot_suffixes):
                fail_codes.append(code)

    print(f"\n{'='*60}")
    print(f"完成: 成功 {total_ok} / {len(codes) * len(shot_suffixes)} 张")
    if fail_codes:
        print(f"存在失败图片的商品编码: {fail_codes}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fail_txt = Path(output_dir) / f"failed_codes_{ts}.txt"
        fail_txt.parent.mkdir(parents=True, exist_ok=True)
        fail_txt.write_text("\n".join(fail_codes), encoding="utf-8")
        print(f"失败编码已保存: {fail_txt}")


def main() -> None:
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


if __name__ == "__main__":
    main()
