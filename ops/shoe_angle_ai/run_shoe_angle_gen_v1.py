# ops/shoe_angle_ai/run_shoe_angle_gen_v1.py
"""批量鞋子产品图视角微调脚本 —— 提示词 v1（本地图 + 自动上传 R2）。

跟 ops/ai_image/legacy/run_shoe_angle_gen.py 是同一条处理路径
（process_one_sku：本地图 → 自动上传 R2 → 一次生成 3 个角度变体），
唯一区别是这里显式传入 v1 提示词（shoe_angle_config_v1.py）：
  - 角度从 5 度加大到 10～15 度
  - 正向提示词加入"必须是真 3D 透视变化，不是 2D 拉伸/挤压"的强调
  - 负向提示词把"禁止 2D 拉伸/挤压"前置强化
用于修复纯侧面鞋款（比如棕色短靴）旋转时被 AI 用横向挤压敷衍了事的问题。

v1 提示词定义在 shoe_angle_config_v1.py，不修改 shoe_angle_config.py
本身（其他已跑通的品类继续用原版）。

用法：
  1. 修改下方"本次运行参数"。
  2. 将鞋子原图放入 INPUT_DIR/<SKU>/1.jpg（文件名可用 INPUT_FILENAME 修改）。
  3. 运行：python ops/shoe_angle_ai/run_shoe_angle_gen_v1.py

输入结构：
  shoes_input/
      SKU001/1.jpg
      SKU002/1.jpg

输出结构：
  shoes_output_v1/
      SKU001/angle_01.png   ← 左转 10°（真 3D 透视）
      SKU001/angle_02.png   ← 右转 10°（真 3D 透视）
      SKU001/angle_03.png   ← 俯角 15°
      SKU002/...

注意：需要在 ops/shoe_angle_ai/shoe_angle_config.py 中填入 R2 写入凭证
（R2_ACCOUNT_ID 等）才能运行 —— v1 的 R2 凭证跟原版共用同一套。
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

from common.ai.image import GrsAIClient
from ops.shoe_angle_ai.shoe_angle_rotate import process_one_sku
from ops.shoe_angle_ai.shoe_angle_config_v1 import (
    SHOE_ANGLE_VARIANTS_V1,
    SHOE_ANGLE_NEGATIVE_PROMPT_V1,
)
from config import GRSAI_API_KEY, GRSAI_HOST

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 输入根目录：内含 <SKU>/<INPUT_FILENAME> 子文件夹
INPUT_DIR      = r"D:\shoes_angle\shoes_input"

# 输出根目录：结果写入 <OUTPUT_DIR>/<SKU>/angle_0N.png
OUTPUT_DIR     = r"D:\shoes_angle\shoes_output_v1"

# SKU 文件夹内的原图文件名（通常是 1.jpg）
INPUT_FILENAME = "1.jpg"

# 并发线程数（建议 2~3；过高触发 API 限流）
MAX_WORKERS = 2

# 每个角度最大重试次数（不含首次）
MAX_RETRIES = 2

# 重试前等待时间（秒）
RETRY_DELAY = 8.0

# 生成后是否删除 R2 上的临时输入文件（True 推荐，节省存储空间）
CLEANUP_R2 = True

# 限速：每次 API 提交后最少等待秒数（0 = 不限速）
# 建议并发 2 时设 2s，并发 3+ 时设 3s
RATE_LIMIT_SLEEP = 2.0

# ============================================================
# Main
# ============================================================


class _RateLimiter:
    """每次 acquire() 之间至少间隔 min_interval 秒（线程安全）。"""

    def __init__(self, min_interval: float) -> None:
        self._lock         = threading.Lock()
        self._last_time    = 0.0
        self._min_interval = min_interval

    def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now   = time.monotonic()
            delta = self._min_interval - (now - self._last_time)
            if delta > 0:
                time.sleep(delta)
            self._last_time = time.monotonic()


def _collect_skus(input_dir: str, input_filename: str) -> list[str]:
    """扫描 input_dir 下的 SKU 子文件夹，找到含 input_filename 的 SKU。"""
    root = Path(input_dir)
    if not root.is_dir():
        print(f"[ERROR] 输入目录不存在: {input_dir}")
        return []
    skus = []
    for sub in sorted(root.iterdir()):
        if sub.is_dir() and (sub / input_filename).is_file():
            skus.append(sub.name)
    return skus


def main() -> None:
    skus = _collect_skus(INPUT_DIR, INPUT_FILENAME)
    if not skus:
        print(f"未发现任何含 '{INPUT_FILENAME}' 的 SKU 子文件夹，请检查 INPUT_DIR。")
        return

    print(f"共发现 {len(skus)} 个 SKU: {skus}")
    print(f"每款生成 3 个角度（v1 提示词）→ 共 {len(skus) * 3} 张图")
    print(f"并发线程: {MAX_WORKERS} / 重试次数: {MAX_RETRIES} / 限速: {RATE_LIMIT_SLEEP}s\n")

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)

    total_ok:  int       = 0
    fail_skus: list[str] = []
    rate_lock = _RateLimiter(RATE_LIMIT_SLEEP)

    def _run(sku: str) -> tuple[str, list[str]]:
        rate_lock.acquire()
        saved = process_one_sku(
            sku=sku,
            input_dir=INPUT_DIR,
            output_dir=OUTPUT_DIR,
            client=client,
            input_filename=INPUT_FILENAME,
            angle_variants=SHOE_ANGLE_VARIANTS_V1,
            negative_prompt=SHOE_ANGLE_NEGATIVE_PROMPT_V1,
            max_retries=MAX_RETRIES,
            retry_delay=RETRY_DELAY,
            cleanup_r2=CLEANUP_R2,
        )
        return sku, saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run, sku): sku for sku in skus}
        for future in as_completed(futures):
            sku, saved = future.result()
            if saved:
                total_ok += len(saved)
            else:
                fail_skus.append(sku)

    # 汇总
    print(f"\n{'='*60}")
    print(f"完成：成功 {total_ok} 张 / 失败 {len(fail_skus)} 款")
    if fail_skus:
        print(f"失败 SKU: {fail_skus}")
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        fail_txt = Path(OUTPUT_DIR) / f"failed_skus_{ts}.txt"
        fail_txt.parent.mkdir(parents=True, exist_ok=True)
        fail_txt.write_text("\n".join(fail_skus), encoding="utf-8")
        print(f"失败列表已保存: {fail_txt}")


if __name__ == "__main__":
    main()
