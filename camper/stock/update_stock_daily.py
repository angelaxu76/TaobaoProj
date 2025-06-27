import os
import re
import psycopg2
from datetime import datetime
from pathlib import Path
from psycopg2.extras import execute_values

# ========== 配置区 ==========
TXT_FOLDER = r"D:\TB\Products\camper\publication\TXT"
PGSQL_CONFIG = {
    "host": "192.168.4.55",
    "port": 5432,
    "user": "postgres",
    "password": "madding2010",
    "dbname": "camper_inventory_db"
}
TABLE_NAME = "camper_inventory"

# ========== 提取 TXT 尺码库存 ==========
def parse_txt_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    code_match = re.search(r"Product CODE:\s*(.+)", content)
    url_match = re.search(r"Product URL:\s*(.+)", content)
    title_match = re.search(r"Product Title:\s*(.+)", content)

    product_code = code_match.group(1).strip() if code_match else "UNKNOWN"
    product_url = url_match.group(1).strip() if url_match else "https://placeholder.url"
    title = title_match.group(1).lower() if title_match else ""

    if "women" in title:
        gender = "women"
    elif "men" in title or "man" in title:
        gender = "men"
    elif "kid" in title or "child" in title:
        gender = "kids"
    else:
        desc_match = re.search(r"Description:\s*(.+?)(?:\n\n|$)", content, re.DOTALL)
        desc = desc_match.group(1).lower() if desc_match else ""
        if "women" in desc:
            gender = "women"
        elif "men" in desc or "man" in desc:
            gender = "men"
        elif "kid" in desc or "child" in desc:
            gender = "kids"
        else:
            gender = "unknown"

    size_block = content.split("Size & EAN Info:")[-1].strip()
    size_lines = [line.strip() for line in size_block.splitlines() if line.strip()]

    rows = []
    print(f"\n📦 商品编码: {product_code} | 性别: {gender}")
    for line in size_lines:
        match = re.match(r"尺码:\s*(\d+)[^|]*\|\s*EAN:\s*\d+\s*\|\s*可用:\s*\w+\s*\|\s*库存:\s*(\d+)", line)
        if match:
            size, qty = match.groups()
            qty = int(qty)
            print(f"  - 尺码 {size}: 库存 {qty}")
            rows.append((
                product_code, product_url, size, gender,
                qty,     # stock_quantity
                None,    # last_stock_quantity
                datetime.now()
            ))
        else:
            print(f"⚠️ 无法解析行: {line}")
    return rows

# ========== 主流程 ==========
def main():
    all_rows = []
    txt_files = list(Path(TXT_FOLDER).glob("*.txt"))
    for file in txt_files:
        all_rows.extend(parse_txt_file(file))

    if not all_rows:
        print("⚠️ 没有可更新的数据。")
        return

    insert_query = f"""
        INSERT INTO {TABLE_NAME} (
            product_code, product_url, size, gender,
            stock_quantity, last_stock_quantity, last_checked
        )
        VALUES %s
        ON CONFLICT (product_code, size)
        DO UPDATE SET
            last_stock_quantity = {TABLE_NAME}.stock_quantity,
            stock_quantity = EXCLUDED.stock_quantity,
            product_url = EXCLUDED.product_url,
            gender = EXCLUDED.gender,
            last_checked = EXCLUDED.last_checked
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    with conn.cursor() as cur:
        execute_values(cur, insert_query, all_rows)
        conn.commit()
    conn.close()

    print(f"\n✅ 共处理并写入/更新记录数: {len(all_rows)}")

if __name__ == "__main__":
    main()
