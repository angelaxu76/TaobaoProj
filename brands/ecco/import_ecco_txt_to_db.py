import os
from common_taobao.txt_parser import extract_product_info
import psycopg2
import pandas as pd
from pathlib import Path
from datetime import datetime
from config import PGSQL_CONFIG, ECCO

# === 配置目录 ===
TXT_DIR = ECCO["TXT_DIR"]
STORE_DIR = ECCO["STORE_DIR"]
TABLE_NAME = "ecco_inventory"

# === 加载 SKU 映射表 ===
def load_sku_mapping_from_store(store_path: Path):
    sku_map = {}
    for file in store_path.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        print(f"📂 读取 SKU 映射文件: {file.name}")
        df = pd.read_excel(file, dtype=str)
        for _, row in df.iterrows():
            spec = str(row.get("sku规格", "")).replace("，", ",").strip().rstrip(",")
            skuid = str(row.get("skuID", "")).strip()
            if spec and skuid:
                sku_map[spec] = skuid
    return sku_map

# === 提取字段函数 ===
def extract_line(lines, key):
    for line in lines:
        if line.startswith(key):
            return line.strip().split(":", 1)[-1].strip()
    return ""

def parse_price(price_line):
    try:
        return float(price_line.replace("£", "").strip())
    except:
        return None

# === 导入逻辑 ===
def process_txt_and_import(stock_name, sku_map, conn):
    cursor = conn.cursor()
    processed = 0

    for txt_file in TXT_DIR.glob("*.txt"):
        print(f"\n📄 处理文件: {txt_file.name}")
        with open(txt_file, encoding="utf-8") as f:
            lines = f.readlines()

        code = extract_line(lines, "Product Code")
        color = extract_line(lines, "Color Code")
        product_code = f"{code}-{color}"
        gender = "Women" if "WOMEN" in txt_file.name.upper() else "Men"
        price = parse_price(extract_line(lines, "原价"))
        discount = parse_price(extract_line(lines, "折扣价"))
        url = ""  # ECCO 暂无单独商品链接，留空或可以后补充

        stock_start = -1
        for i, line in enumerate(lines):
            if line.strip() == "Available Sizes:":
                stock_start = i + 1
                break

        if stock_start == -1:
            print("⚠️ 未找到尺码库存段，跳过")
            continue

        for line in lines[stock_start:]:
            if line.strip() == "" or ":" not in line:
                break
            try:
                size, status = [s.strip() for s in line.split(":")]
                stock_quantity = 3 if status == "有货" else 0
                spec_key = f"{product_code},{size}"
                skuid = sku_map.get(spec_key)
                is_published = skuid is not None

                values = (
                    product_code, url, size, gender,
                    stock_quantity, None, price, discount,
                    datetime.now(), is_published
                )

                cursor.execute(f"""
                    INSERT INTO {TABLE_NAME} (
                        product_name, product_url, size, gender,
                        stock_quantity, last_stock_quantity,
                        price_gbp, adjusted_price_gbp,
                        last_checked, is_published
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (product_name, size) DO UPDATE SET
                        stock_quantity = EXCLUDED.stock_quantity,
                        adjusted_price_gbp = EXCLUDED.adjusted_price_gbp,
                        price_gbp = EXCLUDED.price_gbp,
                        last_checked = EXCLUDED.last_checked,
                        is_published = EXCLUDED.is_published;
                """, values)

                print(f"✅ 插入成功: {product_code} - {size}, 库存: {stock_quantity}")
                processed += 1
            except Exception as e:
                print(f"❌ 插入失败: {line.strip()} - 错误: {e}")

        conn.commit()

    print(f"\n📦 共插入或更新 {processed} 条记录")

# === 主执行入口 ===
def run():
    print("🔌 正在连接数据库...")
    try:
        with psycopg2.connect(**PGSQL_CONFIG) as conn:
            print("✅ 数据库连接成功")
            for store_folder in STORE_DIR.iterdir():
                if store_folder.is_dir():
                    stock_name = store_folder.name
                    print(f"\n🏬 处理店铺: {stock_name}")
                    sku_mapping = load_sku_mapping_from_store(store_folder)
                    process_txt_and_import(stock_name, sku_mapping, conn)
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")

if __name__ == "__main__":
    run()
