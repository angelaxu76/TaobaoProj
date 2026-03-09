"""
从 Excel 文件下载图片到指定目录。

图片命名规则：{id}_{gender}_{age}_{region}.jpg
必需列：id, url, gender, age, region

用法：修改下方 CONFIG 后直接运行。
"""

import os
import re
import time
import requests
import pandas as pd
from pathlib import Path

# ─── 运行参数 ───────────────────────────────────────────────────────────────
INPUT_EXCEL = r"D:\TB\AI生成图片\AI_models_sorted.xlsx"   # 输入 Excel 路径
OUTPUT_DIR  = r"D:\TB\AI生成图片\model_images"  # 图片保存目录

# Excel 列名映射（如列名不同可在此修改）
COL_ID     = "id"
COL_URL    = "url"
COL_GENDER = "gender"
COL_AGE    = "age"
COL_REGION = "region"

# 下载参数
TIMEOUT        = 20    # 每张图片请求超时（秒）
RETRY_TIMES    = 3     # 失败重试次数
RETRY_INTERVAL = 2     # 重试间隔（秒）
SKIP_EXISTING  = True  # True = 已存在则跳过，False = 覆盖
# ────────────────────────────────────────────────────────────────────────────


def sanitize_filename(value: str) -> str:
    """去除文件名中的非法字符。"""
    return re.sub(r'[\\/:*?"<>|]', "_", str(value).strip())


def build_filename(row: pd.Series) -> str:
    """根据行数据构建文件名（不含扩展名）。"""
    parts = [
        sanitize_filename(row[COL_ID]),
        sanitize_filename(row[COL_GENDER]),
        sanitize_filename(row[COL_AGE]),
        sanitize_filename(row[COL_REGION]),
    ]
    return "_".join(parts)


def guess_ext(url: str, content_type: str = "") -> str:
    """从 URL 或 Content-Type 推断图片扩展名，默认 .jpg。"""
    url_path = url.split("?")[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if url_path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def download_image(url: str, save_path: str) -> bool:
    """下载单张图片，失败自动重试。返回是否成功。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"    [尝试 {attempt}/{RETRY_TIMES}] 失败：{e}")
            if attempt < RETRY_TIMES:
                time.sleep(RETRY_INTERVAL)
    return False


def main():
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"读取 Excel：{INPUT_EXCEL}")
    df = pd.read_excel(INPUT_EXCEL, dtype={COL_ID: str})

    required_cols = {COL_ID, COL_URL, COL_GENDER, COL_AGE, COL_REGION}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少必需列：{missing}")

    total   = len(df)
    success = 0
    skipped = 0
    failed  = 0

    for idx, row in df.iterrows():
        url = str(row[COL_URL]).strip()
        if not url or url.lower() == "nan":
            print(f"[{idx+1}/{total}] 跳过（URL 为空）：id={row[COL_ID]}")
            skipped += 1
            continue

        filename  = build_filename(row)
        ext       = guess_ext(url)
        save_path = output_dir / f"{filename}{ext}"

        if SKIP_EXISTING and save_path.exists():
            print(f"[{idx+1}/{total}] 已存在，跳过：{save_path.name}")
            skipped += 1
            continue

        print(f"[{idx+1}/{total}] 下载：{save_path.name}")
        ok = download_image(url, str(save_path))
        if ok:
            print(f"    ✓ 保存至：{save_path}")
            success += 1
        else:
            print(f"    ✗ 下载失败，URL：{url}")
            failed += 1

    print("\n─── 完成 ───")
    print(f"  成功：{success}  跳过：{skipped}  失败：{failed}  共：{total}")
    print(f"  保存目录：{output_dir.resolve()}")


if __name__ == "__main__":
    main()
