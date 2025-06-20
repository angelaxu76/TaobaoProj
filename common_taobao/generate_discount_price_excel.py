
import psycopg2
import openpyxl
from config import CLARKS

def convert_price(gbp_price):
    try:
        gbp_price = float(gbp_price)
        return round((gbp_price * 1.2 + 18) * 1.1 * 1.2 * 9.7, 2)
    except Exception as e:
        print(f"[DEBUG] 价格换算失败: {gbp_price}, 错误: {e}")
        return 0.0

def export_discount_price_excel(brand: str):
    config = CLARKS if brand.lower() == "clarks" else None
    if not config:
        print(f"❌ 不支持的品牌: {brand}")
        return

    PGSQL = config["PGSQL_CONFIG"]
    OUTPUT_FILE = config["OUTPUT_DIR"] / "价格导出_商品编码.xlsx"

    try:
        conn = psycopg2.connect(**PGSQL)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT product_name,
                   MIN(LEAST(
                       COALESCE(original_price_gbp, 9999),
                       COALESCE(discount_price_gbp, 9999)
                   )) AS lowest_price
            FROM {config["TABLE_NAME"]}
            WHERE (original_price_gbp > 0 OR discount_price_gbp > 0)
            GROUP BY product_name
        """)

        results = cursor.fetchall()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "价格"
        ws.append(["商品编码", "优惠后价"])

        for product_code, gbp in results:
            if not gbp or gbp == 0:
                continue
            rmb = convert_price(gbp)
            ws.append([product_code, rmb])

        wb.save(OUTPUT_FILE)
        print(f"✅ 价格 Excel 已导出: {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ 导出失败: {e}")
