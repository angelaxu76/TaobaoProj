import psycopg2
import pandas as pd
from math import floor
from config import CAMPER, CLARKS, ECCO, GEOX

BRAND_MAP = {
    "camper": CAMPER,
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def calculate_prices(row, delivery_cost=7, exchange_rate=9.7):
    original = row["original_price_gbp"] or 0
    discount = row["discount_price_gbp"] or 0
    if original > 0 and discount > 0:
        low = min(original, discount)
        high = max(original, discount)
        #base_price = min(low * 1.1, high)
        base_price = min(low , high)
    else:
        base_price = discount if discount > 0 else original

    untaxed = (base_price * 0.75 + delivery_cost) * 1.15 * exchange_rate
    untaxed = floor(untaxed / 10) * 10
    retail = untaxed * 1.45
    retail = floor(retail / 10) * 10
    return pd.Series([untaxed, retail], index=["未税价格", "零售价"])


def export_channel_price_excel(brand: str):
    config = BRAND_MAP[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_name
        FROM {table_name}
        WHERE is_published = TRUE AND channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_name": "first"
    }).reset_index()

    df_prices = df_grouped.join(df_grouped.apply(calculate_prices, axis=1))
    df_prices_full = df_prices[["channel_product_id", "product_name", "未税价格", "零售价"]]
    df_prices_full.columns = ["渠道产品ID", "商家编码", "未税价格", "零售价"]

    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices.xlsx"
    df_prices_full.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细: {out_path}")


def export_all_sku_price_excel(brand: str):
    config = BRAND_MAP[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    exclude_file = config["BASE"] / "document" / "excluded_product_names.txt"
    excluded_names = set()
    if exclude_file.exists():
        with open(exclude_file, "r", encoding="utf-8") as f:
            excluded_names = set(line.strip().upper() for line in f if line.strip())

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_name
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_name": "first"
    }).reset_index()

    df_prices = df_grouped.join(df_grouped.apply(calculate_prices, axis=1))
    df_prices["product_name"] = df_prices["product_name"].astype(str).str.strip().str.upper()
    df_prices_filtered = df_prices[~df_prices["product_name"].isin(excluded_names)]

    df_sku = df_prices_filtered[["product_name", "零售价"]]
    df_sku.columns = ["商家编码", "优惠后价"]

    # 分割保存每个最多150行
    max_rows = 150
    total_parts = (len(df_sku) + max_rows - 1) // max_rows

    for i in range(total_parts):
        part_df = df_sku.iloc[i * max_rows: (i + 1) * max_rows]
        out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_sku_price_part{i+1}.xlsx"
        part_df.to_excel(out_path, index=False)
        print(f"✅ 导出: {out_path}（共 {len(part_df)} 条）")
