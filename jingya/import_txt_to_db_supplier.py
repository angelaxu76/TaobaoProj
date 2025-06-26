import os
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import CAMPER, CLARKS, ECCO, GEOX

BRAND_MAP = {
    "camper": CAMPER,
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def parse_txt_file(txt_path: Path) -> list:
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {}
    size_detail_map = {}

    for line in lines:
        if line.startswith("Product Code:"):
            info["product_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product URL:"):
            info["product_url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Gender:"):
            info["gender"] = line.split(":", 1)[1].strip()
        elif line.startswith("Price:"):
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
                if len(parts) == 3:
                    size, stock_count, ean = parts
                    size_detail_map[size] = {
                        "stock_count": int(stock_count),
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
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
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

    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            sql = f"""
                INSERT INTO {table_name} (
                    product_name, product_url, size, gender,
                    ean, stock_count,
                    original_price_gbp, discount_price_gbp, is_published
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_name, size)
                DO UPDATE SET
                    ean = EXCLUDED.ean,
                    stock_count = EXCLUDED.stock_count,
                    original_price_gbp = EXCLUDED.original_price_gbp,
                    discount_price_gbp = EXCLUDED.discount_price_gbp,
                    gender = EXCLUDED.gender,
                    last_checked = CURRENT_TIMESTAMP
            """
            execute_batch(cur, sql, all_records, page_size=100)
    print(f"✅ [{brand_name.upper()}] 已成功导入 TXT 到数据库")

if __name__ == "__main__":
    import_txt_to_db_supplier("camper")