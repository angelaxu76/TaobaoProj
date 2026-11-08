# -*- coding: utf-8 -*-
"""
导出已发布商品的颜色，用于批量更新之前发布的商品颜色
（之前发布时颜色填的是商品编码，客户看不懂）。

列：渠道产品id、商品编码、颜色
  - 一个渠道产品id 下有多个颜色编码（合并多色发布）时，每个编码一行

颜色来源：
  - 通用品牌：库存表 color 字段（导入 TXT 时已翻译成中文）
  - Barbour：barbour_products.color（英文，多个站点取 source_rank 最优的一条），
             用发布 Excel 同一个 map_color() 翻译

用法：修改下方参数后直接运行
  BRANDS   = 要导出的品牌
  IDS_FILE = None → 导出该品牌全部已发布商品
             指定文件 → 只导出文件里的渠道产品id（.txt 每行一个；.xlsx 读"渠道产品id"列，没有则读第一列）
输出：{OUTPUT_DIR}/color_update_{brand}.xlsx
      若指定了 IDS_FILE，查不到的 id 写在"未找到"sheet
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from config import BRAND_CONFIG
from common.publication.excel_columns import COLOR_COLUMN

# ==== 参数 ====
BRANDS = ["barbour"]
IDS_FILE: str | None = None    # 例：r"D:\TB\Products\barbour\document\color_update_ids.xlsx"
# ==============

ID_COLUMN = "渠道产品id"
CODE_COLUMN = "商品编码"

_SQL_COMMON = """
    SELECT TRIM(channel_product_id)  AS cpid,
           UPPER(TRIM(product_code)) AS code,
           MIN(color)                AS color
    FROM {table}
    WHERE COALESCE(TRIM(channel_product_id), '') <> ''
    GROUP BY 1, 2
"""

_SQL_BARBOUR = """
    WITH pub AS (
        SELECT DISTINCT TRIM(channel_product_id) AS cpid, UPPER(TRIM(product_code)) AS code
        FROM barbour_inventory
        WHERE COALESCE(TRIM(channel_product_id), '') <> ''
    ),
    col AS (
        SELECT DISTINCT ON (UPPER(TRIM(product_code)))
               UPPER(TRIM(product_code)) AS code, color
        FROM barbour_products
        WHERE COALESCE(TRIM(color), '') <> ''
        ORDER BY UPPER(TRIM(product_code)), source_rank NULLS LAST, updated_at DESC
    )
    SELECT pub.cpid, pub.code, col.color
    FROM pub LEFT JOIN col ON col.code = pub.code
"""


def load_channel_product_ids(path: str | Path) -> list[str]:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str)
        col = ID_COLUMN if ID_COLUMN in df.columns else df.columns[0]
        values = df[col].tolist()
    else:
        values = path.read_text(encoding="utf-8").splitlines()
    ids = [str(v).strip().removesuffix(".0") for v in values if str(v).strip() and str(v) != "nan"]
    return list(dict.fromkeys(ids))


def _query(brand: str) -> pd.DataFrame:
    cfg = BRAND_CONFIG[brand]
    pg = cfg["PGSQL_CONFIG"]
    engine = create_engine(
        f"postgresql+psycopg2://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['dbname']}"
    )
    sql = _SQL_BARBOUR if brand == "barbour" else _SQL_COMMON.format(table=cfg["TABLE_NAME"])
    with engine.connect() as conn:
        df = pd.read_sql_query(text(sql), conn)

    if brand == "barbour":
        from brands.barbour.common.generate_publication_excel import map_color
        df["color"] = df["color"].map(lambda c: map_color(c) if isinstance(c, str) and c.strip() else None)
    return df


def export_color_update_excel(brand: str, channel_product_ids: list[str] | None = None) -> Path:
    brand = brand.lower()
    df = _query(brand)

    not_found: list[str] = []
    if channel_product_ids:
        found_ids = set(df["cpid"])
        not_found = [i for i in channel_product_ids if i not in found_ids]
        df = df[df["cpid"].isin(set(channel_product_ids))]

    no_color = df["color"].isna() | (df["color"].astype(str).str.strip() == "")
    df_out = (
        df[~no_color]
        .rename(columns={"cpid": ID_COLUMN, "code": CODE_COLUMN, "color": COLOR_COLUMN})
        .sort_values([ID_COLUMN, CODE_COLUMN])
    )

    out_file = BRAND_CONFIG[brand]["OUTPUT_DIR"] / f"color_update_{brand}.xlsx"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_file) as writer:
        df_out.to_excel(writer, sheet_name="颜色", index=False)
        if not_found:
            pd.DataFrame({ID_COLUMN: not_found}).to_excel(writer, sheet_name="未找到", index=False)

    msg = f"✅ [{brand}] 导出 {len(df_out)} 行 → {out_file}"
    if no_color.any():
        msg += f"\n   ⚠️ {int(no_color.sum())} 行无颜色已跳过（多为已下架无 TXT 的商品）"
    if not_found:
        msg += f"\n   ⚠️ {len(not_found)} 个渠道产品id 在库中未找到（见'未找到' sheet）"
    print(msg)
    return out_file


if __name__ == "__main__":
    ids = load_channel_product_ids(IDS_FILE) if IDS_FILE else None
    for b in BRANDS:
        export_color_update_excel(b, ids)
