from __future__ import annotations

import pandas as pd
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from config import BRAND_CONFIG  # 全局配置字典

# —— 按品牌定义字段映射 ——
FIELD_MAP: Dict[str, Dict[str, str]] = {
    "clarks": {
        "code_col": "product_code",
        "price_col": "original_price_gbp",
        "adjusted_col": "discount_price_gbp",
        "stock_col": "stock_status",
    },
    "ecco": {
        "code_col": "product_code",
        "price_col": "original_price_gbp",
        "adjusted_col": "discount_price_gbp",
        "stock_col": "stock_status",
    },
    "geox": {
        "code_col": "product_code",
        "price_col": "original_price_gbp",
        "adjusted_col": "discount_price_gbp",
        "stock_col": "stock_status",
    },
    "camper": {
        "code_col": "product_code",
        "price_col": "original_price_gbp",
        "adjusted_col": "discount_price_gbp",
        "stock_col": "stock_count",
    },
}

SQL_TEMPLATE = """
SELECT
    {code_col}         AS product_code,
    %(brand)s          AS brand,
    {price_col}        AS price,
    {adjusted_col}     AS adjusted_price,
    size,
    {stock_col}        AS stock_field
FROM {table}
WHERE {price_col} IS NOT NULL
  AND {adjusted_col} IS NOT NULL;
"""

TODAY_STR = datetime.now().strftime("%Y%m%d")
OUTPUT_FILE = Path(f"D:/TB/Products/discount_analysis/discount_stock_{TODAY_STR}.xlsx")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

TARGET_STORES = ["英国伦敦代购2015", "五小剑"]


def fetch_brand_df(brand: str) -> pd.DataFrame:
    cfg: Dict[str, Any] = BRAND_CONFIG[brand]
    fields = FIELD_MAP[brand]

    sql = SQL_TEMPLATE.format(
        code_col=fields["code_col"],
        price_col=fields["price_col"],
        adjusted_col=fields["adjusted_col"],
        stock_col=fields["stock_col"],
        table=cfg["TABLE_NAME"],
    )

    with psycopg2.connect(**cfg["PGSQL_CONFIG"]) as conn, conn.cursor() as cur:
        cur.execute(sql, {"brand": brand})
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]

    df = pd.DataFrame(rows, columns=columns)

    df = df[df["price"].notna() & df["adjusted_price"].notna()]
    df = df[df["price"] > 0]

    df["discount_rate"] = (1 - df["adjusted_price"] / df["price"]).round(3)

    if brand == "camper":
        df["in_stock_flag"] = df["stock_field"].astype(float) > 0
    else:
        df["in_stock_flag"] = df["stock_field"].astype(str) == "有货"

    return df


def filter_and_group(df: pd.DataFrame) -> pd.DataFrame:
    df = df.query("discount_rate >= 0.30 and in_stock_flag")

    grouped = (
        df.groupby("product_code")
        .agg(
            brand=("brand", "first"),
            discount_rate=("discount_rate", "mean"),
            sizes_in_stock=("size", "nunique"),
        )
        .reset_index()
    )

    return grouped.query("sizes_in_stock >= 4")


def enrich_with_item_ids(df: pd.DataFrame, pg_cfg: Dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        for store in TARGET_STORES:
            df[store] = None
        return df

    codes = df["product_code"].tolist()
    query = (
        "SELECT product_code, stock_name, item_id "
        "FROM all_inventory "
        "WHERE product_code = ANY(%s) "
        f"AND stock_name IN ({', '.join(['%s'] * len(TARGET_STORES))})"
    )

    params = [codes] + TARGET_STORES

    with psycopg2.connect(**pg_cfg) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    df_item = pd.DataFrame(rows, columns=["product_code", "stock_name", "item_id"])
    pivot = (
        df_item.pivot_table(index="product_code", columns="stock_name", values="item_id", aggfunc="first")
        .reset_index()
    )
    pivot.columns.name = None

    df = df.merge(pivot, how="left", on="product_code")

    for store in TARGET_STORES:
        if store not in df.columns:
            df[store] = None

    return df


def main() -> None:
    writer = pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl")
    total = 0
    written_any = False

    for brand in FIELD_MAP.keys():
        print(f"\n📦 处理 {brand} …")
        try:
            df_raw = fetch_brand_df(brand)
            df_filtered = filter_and_group(df_raw)
            df_final = enrich_with_item_ids(df_filtered, BRAND_CONFIG[brand]["PGSQL_CONFIG"])

            if not df_final.empty:
                df_final.to_excel(writer, sheet_name=brand, index=False)
                print(f"✅ {brand}: {len(df_final)} 条记录写入")
                written_any = True
                total += len(df_final)
            else:
                print(f"⚠️ {brand}: 无符合条件数据")
        except Exception as exc:
            print(f"❌ {brand} 失败: {exc}")

    if written_any:
        writer.close()
        print(f"\n🎉 完成，汇总 {total} 条 → {OUTPUT_FILE}")
    else:
        print("\n⚠️ 所有品牌处理失败或无数据，未生成 Excel 文件")


if __name__ == "__main__":
    main()
