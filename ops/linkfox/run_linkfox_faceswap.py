"""
批量 LinkFox AI换模特-2.0 脚本。

原理：以原始模特拍摄图为底（imageUrl），通过 LinkFox 专用接口将模特头部
      替换为目标模特头部，服装/身体结构由接口保留，无需额外 prompt 调优。

用法：
  1. 修改 _session_config.py 中的 BRAND_ROOT 切换品牌。
  2. 修改下方"本次运行参数"区块。
  3. 在 INPUT_FILE 指定的 Excel 第一列填入商品编码（可有表头行）。
  4. 运行：python ops/linkfox/run_linkfox_faceswap.py

稳定配置（API Key、Host、默认后缀等）在 cfg/ai_config.py 修改。

输出文件命名：{code}{原图后缀}_faceswap.jpg
  例：MWX2343BL56_front_1_faceswap.jpg
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/linkfox/
from _session_config import CODES_EXCEL, LINKFOX_DIR

import openpyxl
from common.ai.image.linkfox_client import LinkFoxClient
from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox
from config import (
    LINKFOX_API_KEY, LINKFOX_HOST,
    R2_PUBLIC_PREFIX,
    LINKFOX_SCENE_STRENGTH,
)

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

# 商品编码列表 Excel（第一列为编码）— 路径由 _session_config.py 统一管理
INPUT_FILE  = str(CODES_EXCEL)
HEADER_ROWS = 1         # 跳过的表头行数（0 = 第一行是数据）

# 原始模特拍摄图的 R2 子目录（imageUrl 来源）
# "" 表示根目录；"product_front" 表示 r2_prefix/product_front/{code}{suffix}.jpg
R2_SHOT_SUBDIR = "product_front"

# 原始拍摄图后缀列表（每个后缀对应一张原图，均会生成一张换模特图）
#   ["_front_1"]              → 每款只处理 {code}_front_1.jpg
#   ["_front_1", "_front_2"] → 每款处理两张
SHOT_SUFFIXES = ["_front_1"]

# 本地输出目录 — 路径由 _session_config.py 统一管理
OUTPUT_DIR = str(LINKFOX_DIR)

# 目标模特头部参考图列表（多个 URL 时按商品顺序轮流分配）
TARGET_MODEL_URLS = [
    "https://test-file-ai.linkfox.com//UPLOAD/example/target-model.png",
    # 可添加更多目标模特图（按需替换为真实 URL）
    # "https://...",
]

# 场景/背景参考图（None 表示保持接口默认，不传场景图）
SCENE_IMG_URL: str | None = None

# 场景相似度 [0.0, 1.0]（None 表示不传，接口默认 0.7）
SCENE_STRENGTH = LINKFOX_SCENE_STRENGTH

# 是否输出原始分辨率
GEN_ORI_RES = False

# 是否为真人模特
REAL_MODEL = True

# 每张原图生成输出张数 [1, 4]
OUTPUT_NUM = 1

# 并发线程数（建议 2~5；过高可能触发 API 限流）
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
    print(f"每款处理原图后缀: {SHOT_SUFFIXES}  → 共 {len(codes) * len(SHOT_SUFFIXES)} 张")
    print(f"目标模特图共 {len(TARGET_MODEL_URLS)} 个，按商品顺序轮流分配")
    print(f"输出目录: {OUTPUT_DIR}")

    # 按商品顺序轮流分配目标模特 URL
    model_url_for = {
        code: TARGET_MODEL_URLS[i % len(TARGET_MODEL_URLS)]
        for i, code in enumerate(codes)
    }

    client = LinkFoxClient(api_key=LINKFOX_API_KEY, host=LINKFOX_HOST)

    r2_shot_prefix = (
        f"{R2_PUBLIC_PREFIX.rstrip('/')}/{R2_SHOT_SUBDIR}"
        if R2_SHOT_SUBDIR
        else R2_PUBLIC_PREFIX
    )

    total_ok   = 0
    fail_codes: list[str] = []

    def _run(code: str) -> tuple[str, list[str]]:
        saved = process_one_linkfox(
            code=code,
            client=client,
            r2_prefix=r2_shot_prefix,
            output_dir=OUTPUT_DIR,
            model_image_url=model_url_for[code],
            shot_suffixes=SHOT_SUFFIXES,
            scene_img_url=SCENE_IMG_URL,
            scene_strength=SCENE_STRENGTH,
            gen_ori_res=GEN_ORI_RES,
            real_model=REAL_MODEL,
            output_num=OUTPUT_NUM,
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

    print(f"\n{'=' * 60}")
    print(f"完成: 成功 {total_ok} 张 / 失败 {len(fail_codes)} 款")
    if fail_codes:
        print(f"失败编码: {fail_codes}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fail_txt = Path(OUTPUT_DIR) / f"failed_codes_{ts}.txt"
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        fail_txt.write_text("\n".join(fail_codes), encoding="utf-8")
        print(f"失败编码已保存: {fail_txt}")


if __name__ == "__main__":
    main()
