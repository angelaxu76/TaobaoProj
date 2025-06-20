
import psycopg2
import openpyxl
from config import CLARKS, ECCO, GEOX, CAMPER
from pathlib import Path

# === ✅ 可配置的库存值 ===
IN_STOCK_VALUE = 3
OUT_OF_STOCK_VALUE = 0

def export_skuid_stock_excel(brand: str):
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
    TABLE_NAME = config["TABLE_NAME"]
    OUTPUT_DIR = config["OUTPUT_DIR"]

    try:
        conn = psycopg2.connect(**PGSQL)
        cursor = conn.cursor()

        # 获取所有店铺名（stock_name）
        cursor.execute(f"SELECT DISTINCT stock_name FROM {TABLE_NAME}")
        stock_names = [row[0] for row in cursor.fetchall()]

        for stock_name in stock_names:
            print(f"📦 正在导出店铺: {stock_name}")

            cursor.execute(f"""
                SELECT skuid,
                       MAX(CASE WHEN stock_status = '有货' THEN {IN_STOCK_VALUE} ELSE {OUT_OF_STOCK_VALUE} END) AS stock
                FROM {TABLE_NAME}
                WHERE stock_name = %s AND skuid IS NOT NULL
                GROUP BY skuid
            """, (stock_name,))

            results = cursor.fetchall()
            if not results:
                print(f"⚠️ 店铺 {stock_name} 无有效库存记录")
                continue

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "库存"
            ws.append(["SKUID", "调整后库存"])

            for skuid, stock in results:
                ws.append([skuid, stock])

            output_file = OUTPUT_DIR / f"{stock_name}_库存.xlsx"
            wb.save(output_file)
            print(f"✅ 已导出库存: {output_file}")

        conn.close()
    except Exception as e:
        print(f"❌ 导出库存失败: {e}")
