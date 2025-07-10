
import pandas as pd
import psycopg2
from config import PGSQL_CONFIG, BRAND_CONFIG

# 输出路径定义
OUTPUT_FILE = "D:/TB/Products/all/交叉店铺活跃商品.xlsx"

def clean_code(x):
    try:
        return str(x).split(".")[0].strip()
    except:
        return str(x).strip()

def check_inventory(cur, brand, product_code):
    if brand.lower() not in BRAND_CONFIG:
        return "库存未知"

    config = BRAND_CONFIG[brand.lower()]
    table = config["TABLE_NAME"]
    stock_field = config["FIELDS"].get("stock", "stock_status")

    if brand.lower() == "camper":
        sql = f"SELECT COUNT(DISTINCT size) FROM {table} WHERE product_code = %s AND {stock_field} > 0"
    else:
        sql = f"SELECT COUNT(DISTINCT size) FROM {table} WHERE product_code = %s AND {stock_field} = '有货'"

    cur.execute(sql, (product_code,))
    result = cur.fetchone()
    if result is None or result[0] is None or result[0] == 0:
        return "库存未知"
    elif result[0] < 4:
        return "库存不足"
    else:
        return ""

def export_cross_shop_active_products():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()

    # 获取满足活跃条件的商品
    sql_active = """
    SELECT DISTINCT product_code, product_title, brand
    FROM all_inventory
    WHERE 
        order_count > 2
        OR cart_count > 5
        OR favorite_count > 5
    """
    df = pd.read_sql(sql_active, conn)
    df["product_code"] = df["product_code"].apply(clean_code)
    df["英国伦敦代购2015"] = ""
    df["五小剑"] = ""
    df["库存状态"] = ""

    # 遍历每行商品
    for i, row in df.iterrows():
        code = row["product_code"]
        brand = str(row["brand"]).lower().strip()

        for store in ["英国伦敦代购2015", "五小剑"]:
            cur.execute(
                "SELECT item_id FROM all_inventory WHERE product_code = %s AND stock_name = %s LIMIT 1",
                (code, store)
            )
            result = cur.fetchone()
            if result:
                df.at[i, store] = result[0]

        # 设置库存状态
        df.at[i, "库存状态"] = check_inventory(cur, brand, code)

    df = df.sort_values(by=["brand", "product_code"])
    df = df[["product_code", "product_title", "brand", "英国伦敦代购2015", "五小剑", "库存状态"]]
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"✅ 导出成功：{OUTPUT_FILE}")
    conn.close()

if __name__ == "__main__":
    export_cross_shop_active_products()
