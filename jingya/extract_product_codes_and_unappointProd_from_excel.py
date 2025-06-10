import pandas as pd
import psycopg2

# === 配置 ===
input_file = r"D:\TB\taojingxiao\jingya\GEI.xlsx"
sku_column_name = "sku名称"
distribution_status_column = "铺货状态"
channel_product_id_column = "渠道产品id"

output_dir = r"D:\TB\taojingxiao\jingya"
output_unpublished_file = rf"{output_dir}\unpublished_products.xlsx"

PGSQL_CONFIG = {
    "host": "192.168.4.55",
    "port": 5432,
    "user": "postgres",
    "password": "madding2010",
    "dbname": "camper_inventory_db"
}
TABLE_NAME = "camper_inventory"

# === 提取商品编码 ===
def extract_product_code(sku_name):
    if pd.isna(sku_name):
        return None
    return str(sku_name).split("，")[0].strip()

# === 获取商品性别映射 ===
def fetch_gender_map(codes):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT product_name, gender
        FROM {TABLE_NAME}
        WHERE product_name = ANY(%s)
    """, (codes,))
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

# === 获取指定编码和尺码的库存 ===
def fetch_inventory(codes, sizes):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT product_name, size, stock_quantity
        FROM {TABLE_NAME}
        WHERE product_name = ANY(%s) AND size = ANY(%s)
    """, (codes, sizes))
    rows = cursor.fetchall()
    conn.close()

    inventory = {}
    for product_name, size, qty in rows:
        inventory.setdefault(product_name, {})[size] = qty
    return inventory

# === 主流程 ===
def main():
    df = pd.read_excel(input_file)
    df["商品编码"] = df[sku_column_name].apply(extract_product_code)
    unique_codes = df["商品编码"].dropna().drop_duplicates().tolist()

    gender_map = fetch_gender_map(unique_codes)

    # 根据性别分类商品编码
    groups = {"women": [], "men": []}
    for code in unique_codes:
        gender = gender_map.get(code, "unknown")
        if gender == "women":
            groups["women"].append(code)
        elif gender == "men":
            groups["men"].append(code)

    # 定义尺码列
    size_map = {
        "women": [str(s) for s in range(35, 43)],
        "men": [str(s) for s in range(39, 47)]
    }

    # 为每个性别输出库存 Excel
    for gender, codes in groups.items():
        if not codes:
            continue

        sizes = size_map[gender]
        inventory = fetch_inventory(codes, sizes)

        records = []
        for code in codes:
            row = {"商品编码": code}
            for size in sizes:
                row[size] = inventory.get(code, {}).get(size, 0)
            records.append(row)

        df_out = pd.DataFrame(records)
        output_file = rf"{output_dir}\unique_productCodes_{gender}.xlsx"
        df_out.to_excel(output_file, index=False)
        print(f"✅ 已导出库存表：{output_file}")

    # === 导出未铺货商品 ===
    unpublished_df = df[df[distribution_status_column] == "未铺货"]
    unpublished_df[[channel_product_id_column, distribution_status_column]].to_excel(output_unpublished_file, index=False)
    print(f"✅ 已导出未铺货商品：{output_unpublished_file}")

if __name__ == "__main__":
    main()
