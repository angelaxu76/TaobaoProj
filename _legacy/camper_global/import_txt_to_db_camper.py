import os
import re
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG, TAOBAO_STORES
import requests

# ================== 汇率相关 ==================
def get_exchange_rates():
    """
    获取 GBP 基准的实时汇率，失败时返回默认值。
    """
    api_url = "https://api.exchangerate.host/latest?base=GBP"
    default_rates = {"GBP": 1.0, "EUR": 1.14, "CAD": 1.73, "AUD": 1.95}
    try:
        response = requests.get(api_url, timeout=5)
        data = response.json()
        if "rates" in data:
            print("✅ 已获取实时汇率")
            return data["rates"]
        else:
            print("⚠️ 汇率API返回无效，使用默认值")
            return default_rates
    except Exception as e:
        print(f"⚠️ 获取汇率失败，使用默认值: {e}")
        return default_rates

# ================== 从 URL 检测货币 ==================
def detect_currency_from_url(url: str) -> str:
    if "en_AU" in url:
        return "AUD"
    elif "en_CA" in url:
        return "CAD"
    elif "en_DE" in url:
        return "EUR"
    return "GBP"

# ================== 解析 TXT 文件 ==================
def parse_txt_file(filepath: Path, exchange_rates: dict) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {}
    size_detail_map = {}
    price_currency = None
    source_url = ""

    for line in lines:
        if line.startswith("Product Code:"):
            info["product_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:") or line.startswith("Product URL:"):
            source_url = line.split(":", 1)[1].strip()
            info["product_url"] = source_url
        elif line.startswith("Product Gender:"):
            info["gender"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            price_str = line.split(":", 1)[1].strip()
            info["original_price"] = float(price_str) if price_str else 0.0
        elif line.startswith("Adjusted Price:"):
            discount_str = line.split(":", 1)[1].strip()
            info["discount_price"] = float(discount_str) if discount_str else 0.0
        elif line.startswith("Currency:"):
            price_currency = line.split(":", 1)[1].strip()
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

    # 如果 Currency 缺失，根据 URL 判断
    if not price_currency:
        price_currency = detect_currency_from_url(source_url)

    # 汇率换算，统一转 GBP
    rate = exchange_rates.get(price_currency.upper(), 1.0)
    original_price_gbp = round(info.get("original_price", 0.0) / rate, 2)
    discount_price_gbp = round(info.get("discount_price", 0.0) / rate, 2)

    return {
        "product_code": info.get("product_code"),
        "product_url": info.get("product_url"),
        "gender": info.get("gender"),
        "original_price_gbp": original_price_gbp,
        "discount_price_gbp": discount_price_gbp,
        "size_detail_map": size_detail_map
    }

# ================== 主函数 ==================
def import_camper_global_txt_to_db():
    config = BRAND_CONFIG["camper_global"]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    # 获取实时汇率
    exchange_rates = get_exchange_rates()

    # 扫描 TXT 文件
    txt_files = list(Path(txt_dir).glob("*.txt"))
    if not txt_files:
        print("⚠️ 未找到任何 TXT 文件")
        return

    # 按商品编码聚合
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
        max_price_info = {
            "discount_price_gbp": 0.0,
            "original_price_gbp": 0.0,
            "product_url": "",
            "gender": ""
        }

        for file in files:
            info = parse_txt_file(file, exchange_rates)

            # 记录最高折扣价对应的数据
            if info["discount_price_gbp"] > max_price_info["discount_price_gbp"]:
                max_price_info.update({
                    "discount_price_gbp": info["discount_price_gbp"],
                    "original_price_gbp": info["original_price_gbp"],
                    "product_url": info["product_url"],
                    "gender": info["gender"]
                })

            for size, detail in info["size_detail_map"].items():
                if size not in combined_size:
                    combined_size[size] = {
                        "stock_count": 0,
                        "ean": detail["ean"]
                    }
                combined_size[size]["stock_count"] += detail["stock_count"]

        product_code_global = f"{product_code}_GLOBAL"

        for size, detail in combined_size.items():
            for store_name in TAOBAO_STORES:  # 每个店铺插入一份
                all_records.append((
                    product_code_global,
                    max_price_info["product_url"],
                    size,
                    max_price_info["gender"],
                    "",  # item_id
                    "",  # skuid
                    detail["stock_count"],  # 精确库存
                    max_price_info["original_price_gbp"],
                    max_price_info["discount_price_gbp"],
                    store_name,  # 店铺名
                    False
                ))

    if not all_records:
        print("⚠️ 没有可导入的数据")
        return

    print(f"📥 准备导入记录数: {len(all_records)}")

    # 写入数据库
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
            execute_batch(cur, sql, all_records, page_size=200)

    print(f"✅ Camper Global TXT 数据已成功导入并按店铺分配")

if __name__ == "__main__":
    import_camper_global_txt_to_db()
