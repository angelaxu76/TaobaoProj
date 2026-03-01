"""
批量 AI 虚拟试穿图片生成脚本。

用法：
  1. 在下方 Config 区填写参数。
  2. 在 INPUT_FILE 指定的 Excel 文件第一列填入商品编码（可有表头行）。
  3. 运行：python ops/run_ai_image_generate.py

图片命名规则（URL_MODE 参数）：
  "A" — {code}_flat.jpg / {code}_back.jpg / {code}_detail_1.jpg
  "B" — {code}_flat_1.jpg / {code}_flat_2.jpg / {code}_back.jpg

输出：OUTPUT_DIR/<code>_generate.jpg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from common.ai.image import GrsAIClient
from common.ai.image.vton_pipeline import process_one

# ============================================================
# Config
# ============================================================

GRSAI_API_KEY = "sk-cb2fd749b4f749198a491588a87375ed"
GRSAI_HOST    = "https://grsaiapi.com"

# 商品编码列表 Excel（第一列为编码）
INPUT_FILE  = r"D:\images\ai_gen\codes.xlsx"
HEADER_ROWS = 1   # 跳过的表头行数（0 = 第一行是数据）

# R2 公共前缀（不含尾部斜线）
R2_PREFIX = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev"

# URL 命名模式："A" 或 "B"（见模块文档）
URL_MODE  = "A"
SKIP_BACK = False   # True 时强制跳过 back 图

# img_1：目标模特图（决定人脸与姿态）
TARGET_MODEL_URL = "https://pub-26c1d97a1b2d4ebf9fa6c000f2a9fe13.r2.dev/menmode_1_1.png"

# 背景参考图（可选，None 为纯工作室背景）
BACKGROUND_URL = None

# 款式/领口模式："closed" | "relaxed" | "layered"
STYLE_MODE = "relaxed"

# AI 生成参数
MODEL        = "nano-banana-2"
ASPECT_RATIO = "3:4"
IMAGE_SIZE   = "1K"

NEGATIVE_PROMPT = (
    "badge on sleeve, arm patch, shoulder logo, embroidery on arm, arm brand label, "
    "extra pockets, extra zippers, asymmetric details not in reference, "
    "inner labels, pattern on inner lining, extra inner buttons, "
    "fused garment layers, messy neckline, "
    "evenly spaced buttons, symmetrically aligned buttons, modified collar, "
    "distorted neckline, "
    "lowres, blurry, bad anatomy, deformed fingers, extra limbs, "
    "watermark, text, signature, low quality, artifact."
)

# 本地输出目录
OUTPUT_DIR = r"D:\images\ai_gen\output"

# ============================================================
# Helpers
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


# ============================================================
# Main
# ============================================================


def main():
    if not GRSAI_API_KEY:
        raise ValueError("请在 GRSAI_API_KEY 中填写 API Key。")
    if not TARGET_MODEL_URL:
        raise ValueError("请在 TARGET_MODEL_URL 中填写目标模特图 URL。")

    codes = read_codes_from_excel(INPUT_FILE, HEADER_ROWS)
    if not codes:
        print("未读取到任何商品编码，请检查 INPUT_FILE 和 HEADER_ROWS。")
        return

    print(f"共读取到 {len(codes)} 个商品编码: {codes}")

    client = GrsAIClient(api_key=GRSAI_API_KEY, host=GRSAI_HOST)
    ok_list: list[str] = []
    fail_list: list[str] = []

    for code in codes:
        result = process_one(
            code=code,
            client=client,
            r2_prefix=R2_PREFIX,
            output_dir=OUTPUT_DIR,
            model_url=TARGET_MODEL_URL,
            url_mode=URL_MODE,
            style_mode=STYLE_MODE,
            model=MODEL,
            aspect_ratio=ASPECT_RATIO,
            image_size=IMAGE_SIZE,
            negative_prompt=NEGATIVE_PROMPT,
            background_url=BACKGROUND_URL,
            skip_back=SKIP_BACK,
        )
        (ok_list if result else fail_list).append(code)

    print(f"\n{'='*60}")
    print(f"完成: 成功 {len(ok_list)} / 失败 {len(fail_list)}")
    if fail_list:
        print(f"失败编码: {fail_list}")


if __name__ == "__main__":
    main()
