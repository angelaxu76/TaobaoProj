"""
批量 LinkFox AI换模特-2.0 脚本（官方 API 直连版，不经过紫鸟）。

紫鸟版见 run_linkfox_faceswap.py；两者读同一份 _session_config.py，
输出目录和文件命名相同，同一批编码只需跑其中一个。

用法：
  1. 修改 _session_config.py 中的 BRAND_ROOT 切换品牌。
  2. 设置 API Key（在 https://ai.linkfox.com/usercenter/team/api-guide 生成）：
     优先读环境变量 LINKFOX_DIRECT_API_KEY，未设置时用 _session_config.py 的 LINKFOX_API_KEY。
  3. 在 INPUT_FILE 指定的 Excel 第一列填入商品编码（可有表头行）。
  4. 运行：python ops/linkfox/run_linkfox_faceswap_direct.py

计费：每张 20 点，原分辨率每张 25 点；创建中/生成中任务上限 100 个。

只换头（_session_config.py 的 LINKFOX_PASTE_HEAD_ONLY = True）：
  AI 图头部以外有明显变化时，把被改掉的衣服/配件从原图贴回来；
  没有变化时直接用 AI 图。都不额外扣点。
  未经处理的 AI 图保存在输出目录的 raw_ai/ 下。
  合成失败的图（如背影）不进输出目录，清单写入 head_failed_*.txt。

输出文件命名：{code}{原图后缀}_faceswap.jpg
  例：MWX2343BL56_front_1_faceswap.jpg
"""
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # project root
sys.path.insert(0, _HERE)                                    # ops/linkfox/
from _session_config import (
    CODES_EXCEL, LINKFOX_DIR,
    R2_SHOT_SUBDIR, SHOT_SUFFIXES, TARGET_MODEL_URLS,
    LINKFOX_API_KEY, LINKFOX_SCENE_STRENGTH, LINKFOX_PASTE_HEAD_ONLY,
)

import cv2
import numpy as np
import openpyxl
import requests
from cfg.ai_config import IMAGE_EXT
from common.ai.image.head_composite import composite_head, read_image, write_jpg
from common.ai.image.linkfox_direct_client import LinkFoxDirectClient, MIN_POLL_INTERVAL
from common.ai.image.linkfox_faceswap_pipeline import process_one_linkfox
from config import R2_PUBLIC_PREFIX

# ============================================================
# 本次运行参数（按需修改）
# ============================================================

API_KEY = os.environ.get("LINKFOX_DIRECT_API_KEY") or LINKFOX_API_KEY

# 商品编码列表 Excel（第一列为编码）— 路径由 _session_config.py 统一管理
INPUT_FILE  = str(CODES_EXCEL)
HEADER_ROWS = 1         # 跳过的表头行数（0 = 第一行是数据）

# 本地输出目录 — 路径由 _session_config.py 统一管理
OUTPUT_DIR = str(LINKFOX_DIR)

# 场景/背景参考图（None 表示不传场景图）
SCENE_IMG_URL: str | None = None

# 场景相似度 [0.0, 1.0]（None 表示不传，接口默认 0.7）
SCENE_STRENGTH = LINKFOX_SCENE_STRENGTH

# 是否输出原始分辨率（None = 不传，接口默认 False）
GEN_ORI_RES: bool | None = None

# 原图是否为真人模特，False 为人台（None = 不传，接口默认 True）
REAL_MODEL: bool | None = None

# 每张原图生成输出张数 [1, 4]（None = 不传，接口默认 1）
OUTPUT_NUM: int | None = None

# 轮询间隔（秒），官方要求至少 10 秒
POLL_INTERVAL = MIN_POLL_INTERVAL

# 并发线程数（每个线程同时只有 1 个任务在跑）
MAX_WORKERS = 8

# 只换头模式下，未经处理的 AI 图存放的子目录
RAW_AI_SUBDIR = "raw_ai"

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


def paste_head_onto_original(saved_path: str, r2_prefix: str) -> str:
    """需要时把被 AI 改掉的衣服/配件从原图贴回，结果写到 saved_path。返回失败原因，成功返回空字符串。

    AI 图先移到 raw_ai/，失败时 saved_path 不再存在，避免被后续流程当成品使用。
    """
    path = Path(saved_path)
    shot = path.stem.split("_faceswap")[0]
    raw_path = path.parent / RAW_AI_SUBDIR / path.name
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(raw_path))

    try:
        resp = requests.get(f"{r2_prefix.rstrip('/')}/{shot}{IMAGE_EXT}", timeout=60)
        resp.raise_for_status()
        original = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
        merged, reason = composite_head(original, read_image(str(raw_path)))
        if merged is not None:
            write_jpg(str(path), merged)
        elif not reason:
            shutil.copy2(str(raw_path), str(path))  # 头部以外没变化，直接用 AI 图
        return reason
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def main():
    codes = read_codes_from_excel(INPUT_FILE, HEADER_ROWS)
    if not codes:
        print("未读取到任何商品编码，请检查 INPUT_FILE 和 HEADER_ROWS。")
        return

    print(f"共读取到 {len(codes)} 个商品编码: {codes}")
    print(f"每款处理原图后缀: {SHOT_SUFFIXES}  → 共 {len(codes) * len(SHOT_SUFFIXES)} 张")
    print(f"目标模特图共 {len(TARGET_MODEL_URLS)} 个，按商品顺序轮流分配")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"只换头（保留原图衣服/配件）: {'开' if LINKFOX_PASTE_HEAD_ONLY else '关'}")

    # 按商品顺序轮流分配目标模特 URL
    model_url_for = {
        code: TARGET_MODEL_URLS[i % len(TARGET_MODEL_URLS)]
        for i, code in enumerate(codes)
    }

    client = LinkFoxDirectClient(api_key=API_KEY)

    r2_shot_prefix = (
        f"{R2_PUBLIC_PREFIX.rstrip('/')}/{R2_SHOT_SUBDIR}"
        if R2_SHOT_SUBDIR
        else R2_PUBLIC_PREFIX
    )

    total_ok   = 0
    fail_codes: list[str] = []
    head_failures: list[str] = []

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
            poll_interval=POLL_INTERVAL,
        )
        if not LINKFOX_PASTE_HEAD_ONLY:
            return code, saved

        kept = []
        for path in saved:
            reason = paste_head_onto_original(path, r2_shot_prefix)
            if reason:
                print(f"[{code}] 只换头失败 {Path(path).name}: {reason}")
                head_failures.append(f"{Path(path).name}\t{reason}")
            else:
                print(f"[{code}] 只换头完成 → {path}")
                kept.append(path)
        return code, kept

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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if head_failures:
        head_txt = Path(OUTPUT_DIR) / f"head_failed_{ts}.txt"
        head_txt.write_text("\n".join(head_failures), encoding="utf-8")
        print(f"只换头失败 {len(head_failures)} 张（AI 原图在 {RAW_AI_SUBDIR}/）: {head_txt}")
    if fail_codes:
        print(f"失败编码: {fail_codes}")
        fail_txt = Path(OUTPUT_DIR) / f"failed_codes_{ts}.txt"
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        fail_txt.write_text("\n".join(fail_codes), encoding="utf-8")
        print(f"失败编码已保存: {fail_txt}")


if __name__ == "__main__":
    main()
