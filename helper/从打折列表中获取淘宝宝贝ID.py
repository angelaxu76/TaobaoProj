# -*- coding: utf-8 -*-
"""
脚本功能:
1. 从 discount.xlsx 读取商品编码
2. 从 英国伦敦代购.xlsx 匹配相同商品编码对应的 宝贝ID
3. 输出 TXT 文件: 每行 [商品编码    宝贝ID]
"""

import pandas as pd
import numpy as np
from pathlib import Path

# 输入文件路径
discount_path = Path(r"D:\TB\Products\clarks_jingya\document\store\discount.xlsx")
london_path = Path(r"D:\TB\Products\clarks_jingya\document\store\英国伦敦代购.xlsx")
out_path = Path(r"D:\TB\Products\clarks_jingya\document\store\伦敦代购_折扣_编码到宝贝ID映射.txt")


def normalize_colnames(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def find_best_column(df: pd.DataFrame, candidates) -> str | None:
    cols = list(df.columns)
    for cand in candidates:
        if cand in cols:
            return cand
    # 模糊匹配
    for c in cols:
        for cand in candidates:
            if cand in c:
                return c
    return None


def norm_code(s):
    """商品编码标准化"""
    if pd.isna(s):
        return np.nan
    s = str(s).strip()
    return s.replace(" ", "").upper()


def main():
    # 读取Excel
    discount_df = pd.read_excel(discount_path)
    london_df = pd.read_excel(london_path)

    # 标准化列名
    discount_df = normalize_colnames(discount_df)
    london_df = normalize_colnames(london_df)

    # 列名候选
    product_code_aliases = [
        "product_code", "productcode", "商品编码", "商家编码", "编码", "货号",
        "style_code", "stylecode", "product", "code"
    ]
    item_id_aliases = [
        "宝贝id", "item_id", "itemid", "淘宝id"
    ]

    # 自动识别关键列
    discount_code_col = find_best_column(discount_df, product_code_aliases)
    london_code_col = find_best_column(london_df, product_code_aliases)
    london_itemid_col = find_best_column(london_df, item_id_aliases)

    if not discount_code_col or not london_code_col or not london_itemid_col:
        raise ValueError("❌ 无法识别必要的列名，请检查 Excel 中商品编码和宝贝ID的列名")

    # 统一编码格式
    discount_df["_code_norm"] = discount_df[discount_code_col].map(norm_code)
    london_df["_code_norm"] = london_df[london_code_col].map(norm_code)

    # 过滤空值
    discount_df = discount_df[discount_df["_code_norm"].notna()]
    london_df = london_df[london_df["_code_norm"].notna()]

    # 左连接匹配
    merged = pd.merge(
        discount_df[["_code_norm"]].drop_duplicates(),
        london_df[["_code_norm", london_itemid_col]],
        on="_code_norm",
        how="left"
    )

    merged.rename(columns={"_code_norm": "product_code", london_itemid_col: "item_id"}, inplace=True)

    # 输出TXT
    with open(out_path, "w", encoding="utf-8") as f:
        for _, row in merged.iterrows():
            code = "" if pd.isna(row["product_code"]) else str(row["product_code"])
            item = "" if pd.isna(row["item_id"]) else str(row["item_id"])
            f.write(f"{code}\t{item}\n")

    print(f"✅ 已生成TXT文件: {out_path}")


if __name__ == "__main__":
    main()
