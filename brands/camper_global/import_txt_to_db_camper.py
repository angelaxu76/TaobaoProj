import os
import re
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG

def parse_txt_file(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
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
                if len(parts) == 3:
                    size, stock_count, ean = parts
                    size_detail_map[size] = {
                        "stock_count": int(stock_count),
                        "ean": ean
                    }

    return {
        "product_code": info.get("product_code"),
        "product_url": info.get("product_url"),
        "gender": info.get("gender"),
        "original_price_gbp": info.get("original_price_gbp", 0.0),
        "discount_price_gbp": info.get("discount_price_gbp", 0.0),
        "size_detail_map": size_detail_map
    }

def import_camper_global_txt_to_db():
    config = BRAND_CONFIG["camper_global"]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    txt_files = list(Path(txt_dir).glob("*.txt"))
    product_groups = {}

    for file in txt_files:
        match = re.match(r"(.+?)_([A-Z]{2})\.txt$", file.name)
        if not match:
            continue
        product_code, country = match.group(1), match.group(2)
        product_groups.setdefault(product_code, []).append(file)

    all_records = []

    for product_code, files in product_groups.items():
        combined_size = {}
        merged_info = {}

        for file in files:
            info = parse_txt_file(file)
            merged_info.update(info)  # 只取最后一个国家的元信息用于展示

            for size, detail in info["size_detail_map"].items():
                if size not in combined_size:
                    combined_size[size] = {
                        "stock_count": 0,
                        "ean": detail["ean"]
                    }
                combined_size[size]["stock_count"] += detail["stock_count"]

        # 添加合并后的尺码库存到插入记录
        for size, detail in combined_size.items():
            product_code_global = f"{product_code}_GLOBAL"
            all_records.append((
                product_code_global,
                merged_info.get("product_url", ""),
                size,
                merged_info.get("gender", ""),
                "",  # item_id
                "",  # skuid
                detail["stock_count"],  # ✅ 精确库存
                merged_info.get("original_price_gbp", 0.0),
                merged_info.get("discount_price_gbp", 0.0),
                "GLOBAL",  # stock_name
                False  # is_published
            ))

    if not all_records:
        print("⚠️ 没有可导入的数据")
        return

    print(f"📥 共准备导入合并记录数: {len(all_records)}")

    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            sql = f"""
                INSERT INTO {table_name} (
                    product_code, product_url, size, gender,
                    item_id, skuid,
                    stock_count,
                    original_price_gbp, discount_price_gbp,
                    stock_name, is_published
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_code, size, stock_name)
                DO UPDATE SET
                    stock_count = EXCLUDED.stock_count,
                    original_price_gbp = EXCLUDED.original_price_gbp,
                    discount_price_gbp = EXCLUDED.discount_price_gbp,
                    gender = EXCLUDED.gender,
                    last_checked = CURRENT_TIMESTAMP
            """
            execute_batch(cur, sql, all_records, page_size=100)

    print(f"✅ [CAMPER_GLOBAL] 已成功合并 TXT 并导入数据库")

if __name__ == "__main__":
    import_camper_global_txt_to_db()
