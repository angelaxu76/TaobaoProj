
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from config import PGSQL_CONFIG

# 品牌关键词
BRANDS = ["ecco", "geox", "clarks", "camper", "birkenstock", "barbour", "reiss"]

def extract_brand(title: str) -> str:
    title = str(title).lower()
    for brand in BRANDS:
        if brand in title:
            return brand
    return "其他"

def import_store_products_to_db(base_path: str):
    base = Path(base_path)
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()

    for store_dir in base.iterdir():
        if store_dir.is_dir():
            stock_name = store_dir.name
            print(f"📦 正在处理店铺：{stock_name}")
            for file in store_dir.glob("*.xlsx"):
                try:
                    df = pd.read_excel(file)
                    if "宝贝标题" not in df.columns or "宝贝ID" not in df.columns or "商家编码" not in df.columns:
                        print(f"⚠️ 跳过无效文件: {file.name}")
                        continue

                    records = []
                    for _, row in df.iterrows():
                        item_id = str(row["宝贝ID"]).strip()
                        product_code = str(row["商家编码"]).strip()
                        product_title = str(row["宝贝标题"]).strip()
                        brand = extract_brand(product_title)

                        if not (item_id and product_code and product_title):
                            continue

                        records.append((item_id, product_code, product_title, brand, stock_name))

                    # ✅ 去重：以 item_id 为唯一键，保留最后一条
                    unique_records = {}
                    for rec in records:
                        unique_records[rec[0]] = rec
                    records = list(unique_records.values())

                    if records:
                        sql = """
                            INSERT INTO all_inventory (item_id, product_code, product_title, brand, stock_name)
                            VALUES %s
                            ON CONFLICT (item_id) DO UPDATE
                            SET product_code = EXCLUDED.product_code,
                                product_title = EXCLUDED.product_title,
                                brand = EXCLUDED.brand,
                                stock_name = EXCLUDED.stock_name
                        """
                        execute_values(cur, sql, records)
                        conn.commit()
                        print(f"✅ 导入成功: {file.name} 共 {len(records)} 条")
                except Exception as e:
                    conn.rollback()
                    print(f"❌ 读取文件失败: {file.name}, 错误: {e}")

    cur.close()
    conn.close()
    print("🎉 所有店铺数据导入完成")

# 示例用法（实际调用时取消注释）
# import_store_products_to_db("D:/TB/Products/all")
