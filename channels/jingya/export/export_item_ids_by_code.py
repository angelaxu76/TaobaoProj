# -*- coding: utf-8 -*-
"""
Script Name: export_tb_item_ids.py
Description: 根据商品Excel和商家编码列表导出对应宝贝id列表
Author: YourName
"""

import pandas as pd
import re
import os


def _norm_code(x: str) -> str:
    """标准化商家编码"""
    x = str(x).strip()
    x = re.sub(r"\s+", "", x)
    return x.upper()


def export_item_ids(INPUT_EXCEL: str,
                    PROMO_CODES_TXT: str,
                    OUTPUT_TXT: str):
    """
    导出宝贝id列表

    参数:
        INPUT_EXCEL: 商品Excel路径（必须包含 sheet: items）
        PROMO_CODES_TXT: 商家编码txt路径（每行一个编码，可为空字符串）
        OUTPUT_TXT: 输出宝贝id txt路径
    """

    if not os.path.exists(INPUT_EXCEL):
        raise FileNotFoundError(f"Excel不存在: {INPUT_EXCEL}")

    df = pd.read_excel(INPUT_EXCEL, sheet_name="items")
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

    if "宝贝id" not in df.columns:
        raise ValueError("找不到列：宝贝id")
    if "商家编码" not in df.columns:
        raise ValueError("找不到列：商家编码")

    # ========= 不筛选 → 导出全部 =========
    if not PROMO_CODES_TXT:

        item_ids = (
            df["宝贝id"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        item_ids = item_ids[
            item_ids.str.fullmatch(r"\d+")
        ].drop_duplicates().tolist()

    # ========= 按商家编码筛选 =========
    else:

        if not os.path.exists(PROMO_CODES_TXT):
            raise FileNotFoundError(f"编码文件不存在: {PROMO_CODES_TXT}")

        with open(PROMO_CODES_TXT, "r", encoding="utf-8") as f:
            codes = [_norm_code(line) for line in f if line.strip()]

        code_set = set(codes)

        tmp = df.copy()
        tmp["_code_norm"] = tmp["商家编码"].astype(str).map(_norm_code)

        hit = tmp[tmp["_code_norm"].isin(code_set)]

        item_ids = (
            hit["宝贝id"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        item_ids = item_ids[
            item_ids.str.fullmatch(r"\d+")
        ].drop_duplicates().tolist()

        # 输出未匹配编码
        found_set = set(hit["_code_norm"].unique())
        missing = sorted(code_set - found_set)

        if missing:
            missing_path = OUTPUT_TXT.replace(".txt", "_missing.txt")
            with open(missing_path, "w", encoding="utf-8") as f:
                f.write("\n".join(missing))

            print(f"⚠ 未匹配编码 {len(missing)} 个，已输出: {missing_path}")

    # ========= 写入文件 =========
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(item_ids))

    print(f"✅ 输出宝贝id {len(item_ids)} 条 -> {OUTPUT_TXT}")


# ==============================
# main函数（可直接运行测试）
# ==============================

def main():
    export_item_ids(
        INPUT_EXCEL=r"D:\TB\Products\camper\document\camper.xlsx",
        PROMO_CODES_TXT=r"D:\TB\Products\camper\document\promo_codes.txt",  # 不筛选就传 ""
        OUTPUT_TXT=r"D:\TB\Products\camper\repulibcation\promo_item_ids.txt"
    )


if __name__ == "__main__":
    main()