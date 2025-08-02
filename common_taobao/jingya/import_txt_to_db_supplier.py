import os
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG

# ✅ 库存阈值配置
MIN_STOCK_THRESHOLD = 1  # 小于该值的库存将置为0

def parse_txt_file(txt_path: Path) -> list:
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {}
    size_detail_map = {}

    for line in lines:
        if line.startswith("Product Code:"):
            info["product_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:") or line.startswith("Product URL:"):
            info["product_url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Gender:"):
            info["gender"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            try:
                info["original_price_gbp"] = float(line.split(":", 1)[1].strip())
            except:
                info["original_price_gbp"] = 0.0
        elif line.startswith("Adjusted Price:"):
            try:
                info["discount_price_gbp"] = float(line.split(":", 1)[1].strip())
            except:
                info["discount_price_gbp"] = 0.0
        elif line.startswith("Product Size Detail:"):
            raw = line.split(":", 1)[1]
            for item in raw.split(";"):
                parts = item.strip().split(":")
                if len(parts) == 2:
                    size, stock_count, ean = parts
                    try:
                        stock_count = int(stock_count)
                    except:
                        stock_count = 0

                    # ✅ 如果库存小于阈值，置为0
                    if stock_count < MIN_STOCK_THRESHOLD:
                        stock_count = 0

                    size_detail_map[size] = {
                        "stock_count": stock_count,
                        "ean": ean
                    }

    records = []
    for size, detail in size_detail_map.items():
        records.append((
            info.get("product_code"),
            info.get("product_url"),
            size,
            info.get("gender"),
            detail["ean"],
            detail["stock_count"],
            info.get("original_price_gbp", 0.0),
            info.get("discount_price_gbp", 0.0),
            False  # is_published
        ))

    return records

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
        records = parse_txt_file(file)
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
                    original_price_gbp, discount_price_gbp, is_published
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_batch(cur, sql, all_records, page_size=100)

    print(f"✅ [{brand_name.upper()}] 已完成数据导入并处理库存阈值")

if __name__ == "__main__":
    import_txt_to_db_supplier("camper")
