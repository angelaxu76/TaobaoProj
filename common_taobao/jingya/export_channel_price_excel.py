import os
import psycopg2
import pandas as pd
from config import BRAND_CONFIG
from common_taobao.core.price_utils import calculate_jingya_prices  # ✅ 定价计算核心逻辑

# ============ ✅ 品牌折扣配置 =============
BRAND_DISCOUNT = {
    "camper": 0.75,
    "geox": 0.85,
    "clarks_jingya": 1,
    # "ecco": 0.90,
    # 默认：1.0（无折扣）
}

def get_brand_discount_rate(brand: str) -> float:
    return BRAND_DISCOUNT.get(brand.lower(), 1.0)

def get_brand_base_price(row, brand: str) -> float:
    """
    根据品牌折扣配置计算实际采购价 base_price
    """
    original = row["original_price_gbp"] or 0
    discount = row["discount_price_gbp"] or 0
    base = min(original, discount) if original and discount else (discount or original)
    return base * get_brand_discount_rate(brand)

# ============ ✅ 函数 1：导出所有产品价格 =============
def export_channel_price_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices.xlsx"

    # 🔧 确保输出目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE is_published = TRUE AND channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"📊 原始记录总数: {len(df)}")

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    # ✅ 计算 base_price 并新增一列
    df_grouped["Base Price"] = df_grouped.apply(lambda row: get_brand_base_price(row, brand), axis=1)

    # ✅ 计算定价
    df_grouped[["未税价格", "零售价"]] = df_grouped["Base Price"].apply(
        lambda price: pd.Series(calculate_jingya_prices(price, delivery_cost=7, exchange_rate=9.7))
    )

    # ✅ 导出字段包括 base price
    df_prices_full = df_grouped[["channel_product_id", "product_code", "Base Price", "未税价格", "零售价"]]
    df_prices_full.columns = ["渠道产品ID", "商家编码", "采购价（GBP）", "未税价格", "零售价"]

    df_prices_full.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细: {out_path}")


# ============ ✅ 函数 2：导出指定 TXT 列表价格 =============
def export_channel_price_excel_from_txt(brand: str, txt_path: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"❌ 未找到 TXT 文件: {txt_path}")

    with open(txt_path, "r", encoding="utf-8") as f:
        selected_ids = set(line.strip() for line in f if line.strip())
    if not selected_ids:
        raise ValueError("❌ TXT 文件中没有有效的 channel_product_id")

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["channel_product_id"] = df["channel_product_id"].astype(str)
    df = df[df["channel_product_id"].isin(selected_ids)]

    if df.empty:
        print("⚠️ 没有匹配到任何 channel_product_id。")
        return

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    def compute_price(row):
        base_price = get_brand_base_price(row, brand)
        return pd.Series(calculate_jingya_prices(base_price, 7, 9.7))

    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(compute_price, axis=1)

    df_prices = df_grouped[["channel_product_id", "product_code", "未税价格", "零售价"]]
    df_prices.columns = ["渠道产品ID", "商家编码", "未税价格", "零售价"]

    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices_filtered.xlsx"
    df_prices.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细（指定列表）: {out_path}")


# ============ ✅ 函数 3：导出 SKU 对应的价格（用于淘宝发布） =============
def export_all_sku_price_excel(brand: str):

    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    exclude_file = config["BASE"] / "document" / "excluded_product_codes.txt"
    excluded_names = set()
    if exclude_file.exists():
        with open(exclude_file, "r", encoding="utf-8") as f:
            excluded_names = set(line.strip().upper() for line in f if line.strip())

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    def compute_price(row):
        base_price = get_brand_base_price(row, brand)
        return pd.Series(calculate_jingya_prices(base_price, 7, 9.7))

    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(compute_price, axis=1)

    df_grouped["product_code"] = df_grouped["product_code"].astype(str).str.strip().str.upper()
    df_filtered = df_grouped[~df_grouped["product_code"].isin(excluded_names)]

    df_sku = df_filtered[["product_code", "零售价"]]
    df_sku.columns = ["商家编码", "优惠后价"]

    max_rows = 150
    total_parts = (len(df_sku) + max_rows - 1) // max_rows

    for i in range(total_parts):
        part_df = df_sku.iloc[i * max_rows: (i + 1) * max_rows]
        out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_sku_price_part{i+1}.xlsx"
        part_df.to_excel(out_path, index=False)
        print(f"✅ 导出: {out_path}（共 {len(part_df)} 条）")
