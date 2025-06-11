import os
import re
import psycopg2
from datetime import datetime
from pathlib import Path
from psycopg2.extras import execute_values

# ======================
# ✅ 配置区
# ======================
TXT_FOLDER = r"D:\TB\Products\camper\publication\TXT"
PGSQL_CONFIG = {
    "host": "192.168.4.55",
    "port": 5432,
    "user": "postgres",
    "password": "madding2010",
    "dbname": "camper_inventory_db"
}
TABLE_NAME = "camper_inventory"

# ======================
# 提取性别：根据 URL
# ======================
def detect_gender_from_url(product_url):
    url = product_url.lower()
    if "/women/" in url:
        return "women"
    elif "/men/" in url:
        return "men"
    else:
        return "unknown"

# ======================
# 解析 TXT 文件
# ======================
def parse_txt_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    code_match = re.search(r"Product CODE:\s*(.+)", content)
    url_match = re.search(r"Product URL:\s*(.+)", content)
    price_match = re.search(r"Product price:\s*([\d.]+)GBP", content)

    product_code = code_match.group(1).strip() if code_match else "UNKNOWN"
    product_url = url_match.group(1).strip() if url_match else "https://placeholder.url"
    price_gbp = float(price_match.group(1)) if price_match else None
    gender = detect_gender_from_url(product_url)

    print(f"\n📦 商品编码: {product_code} | 性别: {gender} | 价格: {price_gbp} GBP")

    size_block = content.split("Size & EAN Info:")[-1].strip()
    size_lines = [line.strip() for line in size_block.splitlines() if line.strip()]

    rows = []
    for line in size_lines:
        match = re.match(r"尺码:\s*(\d+)[^|]*\|\s*EAN:\s*\d+\s*\|\s*可用:\s*\w+\s*\|\s*库存:\s*(\d+)", line)
        if match:
            size, quantity = match.groups()
            quantity = int(quantity)
            print(f"  - 尺码 {size}: 库存 {quantity}")
            rows.append((
                product_code,
                product_url,
                size,
                gender,
                quantity,
                None,              # last_stock_quantity
                datetime.now(),
                price_gbp
            ))
        else:
            print(f"⚠️ 无法解析行: {line}")
    return rows

# ======================
# 主函数
# ======================
def main():
    all_rows = []
    txt_files = list(Path(TXT_FOLDER).glob("*.txt"))
    for file in txt_files:
        all_rows.extend(parse_txt_file(file))

    if not all_rows:
        print("⚠️ 没有提取到任何数据，终止执行。")
        return

    insert_query = f"""
        INSERT INTO {TABLE_NAME} (
            product_name, product_url, size,
            gender, stock_quantity,
            last_stock_quantity, last_checked,
            price_gbp
        )
        VALUES %s
        ON CONFLICT (product_name, size)
        DO UPDATE SET
            last_stock_quantity = {TABLE_NAME}.stock_quantity,
            stock_quantity = EXCLUDED.stock_quantity,
            gender = EXCLUDED.gender,
            product_url = EXCLUDED.product_url,
            price_gbp = EXCLUDED.price_gbp,
            last_checked = EXCLUDED.last_checked
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        execute_values(cur, insert_query, all_rows)
        conn.commit()
    conn.close()

    print(f"\n✅ 共处理并写入/更新记录数：{len(all_rows)}")

if __name__ == "__main__":
    main()
