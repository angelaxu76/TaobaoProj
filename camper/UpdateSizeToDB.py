import os
import re
import json
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
DEFAULT_URL = "https://placeholder.url"

# ======================
# 解析 TXT 并提取库存数量
# ======================
def parse_txt_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    code_match = re.search(r"Product CODE:\s*(.+)", content)
    product_code = code_match.group(1).strip() if code_match else "UNKNOWN"
    print(f"\n📦 正在处理商品编码: {product_code}")

    size_block = content.split("Size & EAN Info:")[-1].strip()
    size_lines = [line.strip() for line in size_block.splitlines() if line.strip()]

    insert_rows = []
    for line in size_lines:
        match = re.match(r"尺码:\s*(\d+)[^|]*\|\s*EAN:\s*\d+\s*\|\s*可用:\s*\w+\s*\|\s*库存:\s*(\d+)", line)
        if match:
            size, quantity = match.groups()
            quantity = int(quantity)
            stock_status = "有货" if quantity > 0 else "无货"
            insert_rows.append((product_code, DEFAULT_URL, size, stock_status, quantity, None, datetime.now()))
            print(f"  - 尺码 {size}: 库存 {quantity} ➜ 状态: {stock_status}")
        else:
            print(f"⚠️ 无法解析行: {line}")
    return insert_rows

# ======================
# 主程序
# ======================
def main():
    all_insert_rows = []
    txt_files = list(Path(TXT_FOLDER).glob("*.txt"))
    for file in txt_files:
        rows = parse_txt_file(file)
        all_insert_rows.extend(rows)

    if not all_insert_rows:
        print("⚠️ 未发现任何尺码数据，终止执行。")
        return

    insert_query = f"""
        INSERT INTO {TABLE_NAME} (
            product_name, product_url, size,
            stock_status, stock_quantity,
            last_stock_status, last_checked
        )
        VALUES %s
        ON CONFLICT (product_name, size)
        DO UPDATE SET
            last_stock_status = {TABLE_NAME}.stock_status,
            stock_status = EXCLUDED.stock_status,
            stock_quantity = EXCLUDED.stock_quantity,
            product_url = EXCLUDED.product_url,
            last_checked = EXCLUDED.last_checked
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        execute_values(cur, insert_query, all_insert_rows)
        conn.commit()
    conn.close()

    print(f"\n✅ 共处理 {len(all_insert_rows)} 条记录，库存数量已写入数据库。")

if __name__ == "__main__":
    main()
