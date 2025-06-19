def to_float(val):
    try:
        return float(val.replace('£', '').strip())
    except:
        return None

import os
import psycopg2
from pathlib import Path

def parse_txt(file_path):
    """解析统一格式的商品 TXT 文件，返回字段字典"""
    info = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if ':' in line:
                key, val = line.strip().split(":", 1)
                info[key.strip()] = val.strip()
    return info

def insert_to_db(conn, product):
    """将解析后的商品信息插入数据库（表名需提前创建）"""
    with conn.cursor() as cur:
        cur.execute(
            '''
            INSERT INTO product_info (
                product_code, product_name, product_description, product_gender,
                color, original_price, actual_price, product_url,
                upper_material, lining_material, sole_material, midsole_material,
                fastening_type, trims, sock_material, size_stock, brand
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_code) DO NOTHING
            ''',
            (
                product.get("Product Code"),
                product.get("Product Name"),
                product.get("Product Description"),
                product.get("Product Gender"),
                product.get("Color"),
                product.get("Original Price"),
                product.get("Actual Price"),
                product.get("Product URL"),
                product.get("Upper Material"),
                product.get("Lining Material"),
                product.get("Sole Material"),
                product.get("Midsole Material"),
                product.get("Fastening Type"),
                product.get("Trims"),
                product.get("Sock Material"),
                product.get("Size Stock (EU)"),
                product.get("Brand")
            )
        )
        conn.commit()

def import_txt_to_db(txt_dir: Path, brand: str, conn, stock_name: str = None):
    import os
    import re

    cursor = conn.cursor()
    table_name = f"{brand}_inventory"
    count = 0

    print(f"📁 开始读取目录: {txt_dir}")
    for txt_file in txt_dir.glob("*.txt"):
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            def get_val(key):
                for line in lines:
                    if line.startswith(f"{key}:"):
                        return line.split(":", 1)[1].strip()
                return ""

            product_code = get_val("Product Code")
            product_url = get_val("Product URL")
            gender = get_val("Product Gender")
            original_price = get_val("Original Price").replace("£", "").strip() or None
            actual_price = get_val("Actual Price").replace("£", "").strip() or None
            stock_line = get_val("Size Stock (EU)")

            if not product_code or not stock_line:
                print(f"⚠️ 跳过空数据文件: {txt_file.name}")
                continue

            for pair in stock_line.split(";"):
                if ":" not in pair:
                    continue
                size, stock = map(str.strip, pair.split(":", 1))
                stock_name = stock_name or f"{brand}_default"

                cursor.execute(f"""
                    INSERT INTO {table_name} (
                        product_name, product_url, size, gender,
                        original_price_gbp, discount_price_gbp,
                        stock_status, stock_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (product_name, size, stock_name) DO UPDATE
                    SET
                        product_url = EXCLUDED.product_url,
                        gender = EXCLUDED.gender,
                        original_price_gbp = EXCLUDED.original_price_gbp,
                        discount_price_gbp = EXCLUDED.discount_price_gbp,
                        stock_status = EXCLUDED.stock_status,
                        last_checked = CURRENT_TIMESTAMP
                """, (
                    product_code, product_url, size, gender,
                    to_float(original_price),
                    to_float(actual_price),
                    stock, stock_name
                ))

            count += 1
            print(f"✅ 已导入: {txt_file.name}")

        except Exception as e:
            print(f"❌ 错误处理 {txt_file.name}: {e}")

    conn.commit()
    print(f"🔢 共导入 {count} 个商品")

def import_skuid_from_store_excels(store_dir: Path, brand: str, conn):
    import os
    import pandas as pd

    cursor = conn.cursor()
    table_name = f"{brand}_inventory"

    print(f"📄 开始扫描店铺 Excel：{store_dir}")
    for excel_file in store_dir.glob("*.xlsx"):
        print(f"🔍 处理文件: {excel_file.name}")
        try:
            df = pd.read_excel(excel_file)
            if "sku规格" not in df.columns or "skuID" not in df.columns:
                print(f"⚠️ 文件缺少必要列: {excel_file.name}")
                continue

            for _, row in df.iterrows():
                try:
                    spec = str(row["sku规格"])
                    skuid = str(row["skuID"]).strip()

                    parts = [x.strip() for x in spec.split(",") if x.strip()]
                    if len(parts) < 2:
                        continue
                    product_code, size = parts[:2]

                    update_sql = f'''
                        UPDATE {table_name}
                        SET skuid = %s, is_published = TRUE
                        WHERE product_name = %s AND size = %s
                    '''
                    cursor.execute(update_sql, (skuid, product_code, size))

                except Exception as inner_e:
                    print(f"❌ 行处理失败: {row}\n原因: {inner_e}")

        except Exception as e:
            print(f"❌ 读取失败: {excel_file.name}，原因: {e}")

    conn.commit()
    print(f"✅ SKU ID 导入完成并提交数据库")
    print(f"✅ SKU ID 导入完成并提交数据库")
