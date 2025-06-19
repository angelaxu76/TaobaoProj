import psycopg2
import pandas as pd
from pathlib import Path
from config import PGSQL_CONFIG, ECCO  # ✅ 引入 ECCO 路径配置

# ========== 路径配置 ==========
OUTPUT_DIR = ECCO["OUTPUT_DIR"] / "store_sku_exports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ========== 获取所有店铺名 ==========
def get_all_stores(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT stock_name FROM ecco_inventory WHERE skuid IS NOT NULL")
        return [row[0] for row in cursor.fetchall()]

# ========== 导出某个店铺 Excel ==========
def export_store_to_excel(conn, stock_name):
    query = """
        SELECT skuid, stock_quantity
        FROM ecco_inventory
        WHERE stock_name = %s AND skuid IS NOT NULL
    """
    df = pd.read_sql(query, conn, params=(stock_name,))
    if df.empty:
        return

    df["调整后库存"] = df["stock_quantity"].apply(lambda x: 3 if x > 0 else 0)
    df = df.rename(columns={"skuid": "SKUID"})
    df = df[["SKUID", "调整后库存"]]

    output_path = OUTPUT_DIR / f"{stock_name}_ECCO_skuid库存.xlsx"
    df.to_excel(output_path, index=False)
    print(f"✅ 导出完成：{output_path.name}")

# ========== 主函数 ==========
def main():
    with psycopg2.connect(**PGSQL_CONFIG) as conn:
        stores = get_all_stores(conn)
        for stock_name in stores:
            export_store_to_excel(conn, stock_name)

if __name__ == "__main__":
    main()
