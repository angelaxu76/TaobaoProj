import os
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG
from common_taobao.txt_parser import jingya_parse_txt_file

# ✅ 库存阈值配置
MIN_STOCK_THRESHOLD = 1  # 小于该值的库存将置为0


def import_txt_to_db_supplier(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_CONFIG[brand_name]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    all_records = []
    for file in Path(txt_dir).glob("*.txt"):
        records = jingya_parse_txt_file(file)
        if records:
            all_records.extend(records)

    if not all_records:
        print("⚠️ 没有可导入的数据")
        return

    print(f"📥 共准备导入 {len(all_records)} 条记录")

    # ✅ 连接数据库
    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            # ✅ 清空表（TRUNCATE）
            cur.execute(f"TRUNCATE TABLE {table_name}")
            print(f"🧹 已清空表 {table_name}")

            # ✅ 插入数据
            sql = f"""
                INSERT INTO {table_name} (
                    product_code, product_url, size, gender,
                    ean, stock_count,
                    original_price_gbp, discount_price_gbp, is_published,
                    product_description, product_title, style_category
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            execute_batch(cur, sql, all_records, page_size=100)

    print(f"✅ [{brand_name.upper()}] 已完成数据导入并处理库存阈值")


