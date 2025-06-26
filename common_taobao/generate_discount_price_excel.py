import pandas as pd
import openpyxl
import psycopg2
import math
from pathlib import Path
from config import CLARKS, ECCO, GEOX, CAMPER,BRAND_CONFIG
from common_taobao.core.price_utils import calculate_discount_price_from_float


def export_price_with_itemid(brand: str, store_name: str):


    config = BRAND_CONFIG.get(brand.lower())
    if not config:
        print(f"❌ 不支持的品牌: {brand}")
        return

    store_folder = config["STORE_DIR"] / store_name
    PGSQL = config["PGSQL_CONFIG"]
    table = config["TABLE_NAME"]
    OUTPUT_FILE = config["OUTPUT_DIR"] / f"价格导出_宝贝ID_{store_name}.xlsx"

    # ✅ 自动查找宝贝信息表
    item_mapping_file = None
    for file in store_folder.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        item_mapping_file = file
        break

    if not item_mapping_file:
        print(f"⚠️ 跳过 [{store_name}]：未找到任何宝贝信息 Excel")
        return
    print(f"📄 识别到宝贝信息表: {item_mapping_file.name}")

    try:
        # Step 1️⃣ 读取宝贝ID映射：商家编码 → 宝贝ID
        df = pd.read_excel(item_mapping_file, dtype=str)
        df = df.dropna(subset=["商家编码", "宝贝ID"])
        itemid_map = {
            str(row["商家编码"]).strip(): str(row["宝贝ID"]).strip()
            for _, row in df.iterrows()
        }
        print(f"📦 店铺[{store_name}] 宝贝ID映射数: {len(itemid_map)}")

        # Step 2️⃣ 获取数据库中该店铺商品最低价格
        conn = psycopg2.connect(**PGSQL)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT product_name,
                   MIN(LEAST(
                       COALESCE(original_price_gbp, 9999),
                       COALESCE(discount_price_gbp, 9999)
                   )) AS lowest_price
            FROM {table}
            WHERE stock_name = %s AND is_published = TRUE
            GROUP BY product_name
        """, (store_name,))
        results = cursor.fetchall()
        print(f"🔍 已发布商品数: {len(results)}")

        # Step 3️⃣ 构建导出数据
        export_rows = []
        for product_code, gbp in results:
            if not gbp or gbp == 0:
                continue
            item_id = itemid_map.get(product_code, "")
            if not item_id:
                print(f"⚠️ 未匹配宝贝ID: {product_code}")
                continue
            rmb = calculate_discount_price_from_float(gbp)
            export_rows.append([item_id, "", rmb])

        if not export_rows:
            print(f"⚠️ 无可导出商品: {store_name}")
            return

        # Step 4️⃣ 写入 Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "价格导出"
        ws.append(["宝贝ID", "skuID", "调整后价格"])
        for row in export_rows:
            ws.append(row)

        wb.save(OUTPUT_FILE)
        print(f"✅ 导出成功: {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ 导出失败（{store_name}）: {e}")


def export_store_discount_price(brand: str, store_name: str):
    BRAND_CONFIGS = {
        "clarks": CLARKS,
        "ecco": ECCO,
        "geox": GEOX,
        "camper": CAMPER,
    }

    config = BRAND_CONFIGS.get(brand.lower())
    if not config:
        print(f"❌ 不支持的品牌: {brand}")
        return

    PGSQL = config["PGSQL_CONFIG"]
    table = config["TABLE_NAME"]
    OUTPUT_DIR = config["OUTPUT_DIR"]

    try:
        conn = psycopg2.connect(**PGSQL)
        cursor = conn.cursor()

        # 第一步：获取该店铺已发布商品编码（is_published = True）
        cursor.execute(f"""
            SELECT DISTINCT product_name
            FROM {table}
            WHERE stock_name = %s AND is_published = TRUE
        """, (store_name,))
        published_codes = {row[0] for row in cursor.fetchall()}
        print(f"🔎 已发布商品数: {len(published_codes)}")

        if not published_codes:
            print(f"⚠️ 无商品可导出")
            return

        # 第二步：获取所有商品最低价格
        cursor.execute(f"""
            SELECT product_name,
                   MIN(LEAST(
                       COALESCE(original_price_gbp, 9999),
                       COALESCE(discount_price_gbp, 9999)
                   )) AS lowest_price
            FROM {table}
            WHERE (original_price_gbp > 0 OR discount_price_gbp > 0)
            GROUP BY product_name
        """)
        all_prices = cursor.fetchall()

        # 第三步：只保留该店铺已发布商品
        filtered = [(code, gbp) for code, gbp in all_prices if code in published_codes]

        # 第四步：分页，每页 150 个
        page_size = 150
        page_count = math.ceil(len(filtered) / page_size)

        for i in range(page_count):
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"{store_name}价格"

            ws.append(["商品编码", "优惠后价"])

            page_data = filtered[i * page_size:(i + 1) * page_size]
            for product_code, gbp in page_data:
                if not gbp or gbp == 0:
                    continue
                rmb = calculate_discount_price_from_float(gbp)
                ws.append([product_code, rmb])

            OUTPUT_FILE = OUTPUT_DIR / f"价格导出_仅限_{store_name}_{i+1}.xlsx"
            wb.save(OUTPUT_FILE)
            print(f"✅ 导出分页文件: {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ 导出失败: {e}")