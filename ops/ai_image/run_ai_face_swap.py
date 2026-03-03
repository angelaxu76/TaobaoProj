"""
批量 AI 换脸 + 换背景脚本（服装 100% 保留）。

原理：以商品原始模特拍摄图为底（img_1），只替换人脸/肤色和背景，
      服装纹理/颜色/细节完全不重绘。

用法：
  1. 修改下方"本次运行参数"。
  2. 在 INPUT_FILE 指定的 Excel 第一列填入商品编码（可有表头行）。
  3. 运行：python ops/run_ai_face_swap.py

稳定配置（API Key、模型、负向提示词等）在 cfg/ai_config.py 修改。

输出文件命名：{code}{原图后缀}_faceswap.jpg
  例：MWX2343BL56_1_faceswap.jpg
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import openpyxl
from concurrent.futures import ThreadPoolExecutor, as_completed
from common.ai.image import GrsAIClient
from common.ai.image.faceswap_pipeline import process_one_faceswap
from config import (
    GRSAI_API_KEY, GRSAI_HOST,
    R2_PUBLIC_PREFIX,
    FACESWAP_WHITE_BG_REF_URL,
)

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 商品编码列表 Excel（第一列为编码）
INPUT_FILE  = r"d:\barbour\codes.xlsx"
HEADER_ROWS = 1         # 跳过的表头行数（0 = 第一行是数据）

# 原始模特拍摄图的 R2 子目录（img_1 来源）
# "" 表示根目录直接拼 code；"product_front" 表示 /product_front/{code}{suffix}.jpg
R2_SHOT_SUBDIR = "product_front"

# 原始拍摄图后缀列表（每个后缀对应一张原图，均会生成一张换脸图）
#   ["_front_1"]          → 每款只处理 {code}_front_1.jpg
#   ["_front_1", "_front_2"] → 每款处理两张
SHOT_SUFFIXES = ["_front_1"]

# 本地输出目录
OUTPUT_DIR = r"D:\barbour\faceswap_output"

# 目标模特脸部参考列表（取 cfg 值；多个 URL 时按商品顺序轮流分配）
TARGET_FACE_URLS = [
    # "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_2.png",
    # "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/women_mode_1.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_1.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_2.png",
    "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/men_mode_3.png",
]

# 背景参考图（默认使用纯白参考图；设为 None 时仅依赖 prompt 白底描述）
BACKGROUND_URL = FACESWAP_WHITE_BG_REF_URL

# 并发线程数（建议 2~4；过高可能触发 API 限流）
MAX_WORKERS = 7

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
    print(f"每款处理原图后缀: {SHOT_SUFFIXES}  → 共 {len(codes) * len(SHOT_SUFFIXES)} 张")
    print(f"模特脸部 URL 共 {len(TARGET_FACE_URLS)} 个，按商品顺序轮流分配")

    # 按商品顺序轮流分配模特 URL（thread-safe：只读 dict，提交前已确定）
    face_url_for = {
        code: TARGET_FACE_URLS[i % len(TARGET_FACE_URLS)]
        for i, code in enumerate(codes)
    }

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    total_ok = 0
    fail_codes: list[str] = []

    r2_shot_prefix = f"{R2_PUBLIC_PREFIX.rstrip('/')}/{R2_SHOT_SUBDIR}" if R2_SHOT_SUBDIR else R2_PUBLIC_PREFIX

    def _run(code: str) -> tuple[str, list[str]]:
        saved = process_one_faceswap(
            code=code,
            client=client,
            r2_prefix=r2_shot_prefix,
            output_dir=OUTPUT_DIR,
            target_face_url=face_url_for[code],
            shot_suffixes=SHOT_SUFFIXES,
            background_url=BACKGROUND_URL,
        )
        return code, saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run, code): code for code in codes}
        for future in as_completed(futures):
            code, saved = future.result()
            if saved:
                total_ok += len(saved)
            else:
                fail_codes.append(code)

    print(f"\n{'='*60}")
    print(f"完成: 成功 {total_ok} 张 / 失败 {len(fail_codes)} 款")
    if fail_codes:
        print(f"失败编码: {fail_codes}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fail_txt = Path(OUTPUT_DIR) / f"failed_codes_{ts}.txt"
        fail_txt.write_text("\n".join(fail_codes), encoding="utf-8")
        print(f"失败编码已保存: {fail_txt}")


if __name__ == "__main__":
    main()
