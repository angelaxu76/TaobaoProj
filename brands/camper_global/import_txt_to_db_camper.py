import os
import re
import requests
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG

# === 国家货币映射（用于自动识别币种）===
COUNTRY_CURRENCY = {
    "GB": "GBP",
    "DE": "EUR",
    "CA": "CAD",
    "AU": "AUD"
}

# === 默认汇率（防止 API 调用失败）===
DEFAULT_EXCHANGE_RATES = {
    "GBP": 1.0,
    "EUR": 0.85,
    "CAD": 0.58,
    "AUD": 0.52
}

def get_exchange_rate_to_gbp(base_currency: str) -> float:
    if base_currency == "GBP":
        return 1.0
    try:
        url = f"https://api.exchangerate.host/convert?from={base_currency}&to=GBP"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = data.get("result")
        if isinstance(result, (int, float)) and result > 0:
            return result
    except Exception as e:
        print(f"⚠️ 获取汇率失败: {base_currency} → GBP，使用默认值 {DEFAULT_EXCHANGE_RATES.get(base_currency, 1.0)}，原因: {e}")
    return DEFAULT_EXCHANGE_RATES.get(base_currency, 1.0)

def fetch_all_exchange_rates() -> dict:
    rates = {}
    for country, currency in COUNTRY_CURRENCY.items():
        rate = get_exchange_rate_to_gbp(currency)
        rates[country] = rate
    print("📊 实时汇率表（对 GBP）:", rates)
    return rates

def parse_txt_file(filepath: Path, exchange_rates: dict) -> dict:
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
                info["original_price"] = float(line.split(":", 1)[1].strip())
            except:
                info["original_price"] = 0.0
        elif line.startswith("Adjusted Price:"):
            try:
                info["discount_price"] = float(line.split(":", 1)[1].strip())
            except:
                info["discount_price"] = 0.0
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

    match = re.match(r".+?_([A-Z]{2})\.txt$", filepath.name)
    country_code = match.group(1) if match else "GB"
    currency = COUNTRY_CURRENCY.get(country_code, "GBP")
    rate = exchange_rates.get(country_code, 1.0)

    info["country"] = country_code
    info["original_price_gbp"] = info.get("original_price", 0.0) * rate
    info["discount_price_gbp"] = info.get("discount_price", 0.0) * rate
    info["size_detail_map"] = size_detail_map

    return info

def import_camper_global_txt_to_db():
    config = BRAND_CONFIG["camper_global"]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    exchange_rates = fetch_all_exchange_rates()
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
        max_price_info = {
            "discount_price_gbp": 0.0,
            "original_price_gbp": 0.0,
            "product_url": "",
            "gender": ""
        }

        for file in files:
            info = parse_txt_file(file, exchange_rates)

            if info["discount_price_gbp"] > max_price_info["discount_price_gbp"]:
                max_price_info["discount_price_gbp"] = info["discount_price_gbp"]
                max_price_info["original_price_gbp"] = info["original_price_gbp"]
                max_price_info["product_url"] = info["product_url"]
                max_price_info["gender"] = info["gender"]

            for size, detail in info["size_detail_map"].items():
                if size not in combined_size:
                    combined_size[size] = {
                        "stock_count": 0,
                        "ean": detail["ean"]
                    }
                combined_size[size]["stock_count"] += detail["stock_count"]

        product_code_global = f"{product_code}_GLOBAL"
        for size, detail in combined_size.items():
            all_records.append((
                product_code_global,
                max_price_info["product_url"],
                size,
                max_price_info["gender"],
                "",  # item_id
                "",  # skuid
                detail["stock_count"],
                max_price_info["original_price_gbp"],
                max_price_info["discount_price_gbp"],
                "GLOBAL",
                False
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

    print("✅ [CAMPER_GLOBAL] 已成功导入汇率换算后的最高价格版本")

if __name__ == "__main__":
    import_camper_global_txt_to_db()
