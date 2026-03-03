"""
批量 AI 虚拟试穿图片生成脚本。

用法：
  1. 修改下方"本次运行参数"。
  2. 在 INPUT_FILE 指定的 Excel 第一列填入商品编码（可有表头行）。
  3. 运行：python ops/run_ai_image_generate.py

稳定配置（API Key、模型、后缀名、负向提示词等）统一在 cfg/ai_config.py 修改。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import openpyxl
from concurrent.futures import ThreadPoolExecutor, as_completed
from common.ai.image import GrsAIClient
from common.ai.image.vton_pipeline import process_one
from config import (
    GRSAI_API_KEY, GRSAI_HOST,
    R2_PUBLIC_PREFIX,
    VTON_STYLE_MODE, VTON_TARGET_MODEL_URL, VTON_OUTPUT_DIR,
)

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 商品编码列表 Excel（第一列为编码）
INPUT_FILE  = r"G:\temp\barbour\codes.xlsx"
HEADER_ROWS = 1         # 跳过的表头行数（0 = 第一行是数据）

# URL 命名模式："A" 或 "B"（后缀规则见 cfg/ai_config.py）
URL_MODE  = "A"
SKIP_BACK = False       # True 时强制跳过 back 图

# 款式/领口模式（默认取 cfg 值，如需临时覆盖在此赋值）
STYLE_MODE = VTON_STYLE_MODE    # "closed" | "relaxed" | "layered"

# 目标模特图（默认取 cfg 值，如需换模特在此赋值）
TARGET_MODEL_URL = VTON_TARGET_MODEL_URL

# 背景参考图（None = 纯工作室背景）
BACKGROUND_URL = None

# 本地输出目录（默认取 cfg 值，如需临时输出到其他目录在此赋值）
OUTPUT_DIR = VTON_OUTPUT_DIR

# 并发线程数（API 为 I/O 密集型，建议 2~4；过高可能触发限流）
MAX_WORKERS = 3

# ============================================================
# Main
# ============================================================


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


def main():
    codes = read_codes_from_excel(INPUT_FILE, HEADER_ROWS)
    if not codes:
        print("未读取到任何商品编码，请检查 INPUT_FILE 和 HEADER_ROWS。")
        return

    print(f"共读取到 {len(codes)} 个商品编码: {codes}")

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    ok_list: list[str] = []
    fail_list: list[str] = []

    def _run(code: str) -> tuple[str, bool]:
        result = process_one(
            code=code,
            client=client,
            r2_prefix=R2_PUBLIC_PREFIX,
            output_dir=OUTPUT_DIR,
            model_url=TARGET_MODEL_URL,
            url_mode=URL_MODE,
            style_mode=STYLE_MODE,
            background_url=BACKGROUND_URL,
            skip_back=SKIP_BACK,
        )
        return code, bool(result)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run, code): code for code in codes}
        for future in as_completed(futures):
            code, ok = future.result()
            (ok_list if ok else fail_list).append(code)

    print(f"\n{'='*60}")
    print(f"完成: 成功 {len(ok_list)} / 失败 {len(fail_list)}")
    if fail_list:
        print(f"失败编码: {fail_list}")


if __name__ == "__main__":
    main()
