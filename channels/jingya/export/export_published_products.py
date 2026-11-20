# -*- coding: utf-8 -*-
"""
导出某品牌下所有已发布商品（channel_product_id 非空）列表。

列：渠道产品ID、商品编码、颜色
  - 一个渠道产品ID 下有多个商品编码（合并多色发布）时，每个编码一行
  - 颜色查不到的商品也会保留（颜色列为空）

颜色来源与 export_color_update_excel.py 一致：
  - 通用品牌：库存表 color 字段
  - Barbour：barbour_products.color，经 map_color() 翻译成中文

用法：
  python -m channels.jingya.export.export_published_products barbour
  python -m channels.jingya.export.export_published_products        # 运行后提示输入品牌
输出：{OUTPUT_DIR}/published_products_{brand}.xlsx
"""
import sys
from pathlib import Path

from config import BRAND_CONFIG
from channels.jingya.export.export_color_update_excel import _query

COLUMNS = {"cpid": "渠道产品ID", "code": "商品编码", "color": "颜色"}


def export_published_products(brand: str) -> Path:
    brand = brand.strip().lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"未知品牌 '{brand}'，可选：{', '.join(BRAND_CONFIG)}")

    df = _query(brand)
    df_out = (
        df[list(COLUMNS)]
        .rename(columns=COLUMNS)
        .sort_values(["渠道产品ID", "商品编码"])
        .reset_index(drop=True)
    )

    out_file = BRAND_CONFIG[brand]["OUTPUT_DIR"] / f"published_products_{brand}.xlsx"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_excel(out_file, sheet_name="已发布商品", index=False)

    no_color = df_out["颜色"].isna() | (df_out["颜色"].astype(str).str.strip() == "")
    print(f"✅ [{brand}] 已发布商品 {df_out['渠道产品ID'].nunique()} 个渠道产品ID，"
          f"{len(df_out)} 行 → {out_file}")
    if no_color.any():
        print(f"   ⚠️ {int(no_color.sum())} 行无颜色（已保留，颜色列为空）")
    return out_file


if __name__ == "__main__":
    brand_arg = sys.argv[1] if len(sys.argv) > 1 else input(f"请输入品牌（{', '.join(BRAND_CONFIG)}）：")
    export_published_products(brand_arg)
