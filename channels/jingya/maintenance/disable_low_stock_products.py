import psycopg2
from config import CAMPER, CLARKS, ECCO, GEOX

# ✅ 品牌配置
BRAND_MAP = {
    "camper": CAMPER,
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX,
}

# ✅ 可配置变量
MIN_SIZES = 2  # 如果有效尺码数 <= 这个值，商品下架（库存清零 + is_published=False）

def disable_low_stock_products(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    # ✅ 查询符合条件的 product_code 列表
    query_find = f"""
        SELECT product_code
        FROM {table_name}
        WHERE stock_count > 0 AND is_published = TRUE
        GROUP BY product_code
        HAVING COUNT(size) <= %s;
    """

    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            cur.execute(query_find, (MIN_SIZES,))
            codes = cur.fetchall()

    if not codes:
        print(f"⚠️ [{brand_name.upper()}] 没有找到符合条件的商品")
        return

    product_codes = [c[0] for c in codes]
    print(f"🔍 [{brand_name.upper()}] 找到 {len(product_codes)} 个商品需要清零库存并下架")

    # ✅ 批量更新库存和发布状态
    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            update_sql = f"""
                UPDATE {table_name}
                SET stock_count = 0,
                    is_published = FALSE,
                    last_checked = CURRENT_TIMESTAMP
                WHERE product_code = ANY(%s);
            """
            cur.execute(update_sql, (product_codes,))
            print(f"✅ [{brand_name.upper()}] 已更新 {cur.rowcount} 条记录（库存清零 + 下架）")
