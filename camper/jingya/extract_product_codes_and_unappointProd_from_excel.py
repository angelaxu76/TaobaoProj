import pandas as pd
import psycopg2
from datetime import datetime

# === 配置 ===
input_file = r"D:\TB\taojingxiao\jingya\GEI.xlsx"
sku_column_name = "sku名称"
distribution_status_column = "铺货状态"
channel_product_id_column = "渠道产品id"
price_status_column = "价格状态"

output_dir = r"D:\TB\taojingxiao\jingya"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

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

# === 获取商品性别 ===
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

# === 获取尺码库存 ===
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

# === 获取商品价格 ===
def fetch_price_map(codes):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT product_name, price_gbp
        FROM {TABLE_NAME}
        WHERE product_name = ANY(%s)
    """, (codes,))
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

# === 主程序 ===
def main():
    df = pd.read_excel(input_file, dtype={channel_product_id_column: str})
    df["商品编码"] = df[sku_column_name].apply(extract_product_code)
    unique_codes = df["商品编码"].dropna().drop_duplicates().tolist()

    gender_map = fetch_gender_map(unique_codes)

    # 构建商品编码 → 渠道产品id 映射（唯一）
    code_id_map = df.dropna(subset=["商品编码", channel_product_id_column]) \
                    .drop_duplicates(subset=["商品编码"])[["商品编码", channel_product_id_column]] \
                    .set_index("商品编码")[channel_product_id_column].to_dict()

    # 分类商品编码
    groups = {"women": [], "men": []}
    for code in unique_codes:
        gender = gender_map.get(code, "unknown")
        if gender == "women":
            groups["women"].append(code)
        elif gender == "men":
            groups["men"].append(code)

    # 每类尺码定义
    size_map = {
        "women": [str(s) for s in range(35, 43)],
        "men": [str(s) for s in range(39, 47)]
    }

    # 每类导出库存+价格
    for gender, codes in groups.items():
        if not codes:
            continue
        sizes = size_map[gender]
        inventory = fetch_inventory(codes, sizes)
        price_map = fetch_price_map(codes)

        records = []
        for code in codes:
            row = {
                "商品编码": code,
                "渠道产品id": code_id_map.get(code, ""),
                "价格": price_map.get(code, "")
            }
            for size in sizes:
                row[size] = inventory.get(code, {}).get(size, 0)
            records.append(row)

        df_out = pd.DataFrame(records)
        output_file = rf"{output_dir}\unique_productCodes_{gender}.xlsx"
        df_out.to_excel(output_file, index=False)
        print(f"✅ 已导出库存表：{output_file}")

    # 导出未铺货商品
    unpublished_df = df[df[distribution_status_column] == "未铺货"]
    unpublished_output = rf"{output_dir}\unpublished_products_{timestamp}.xlsx"
    unpublished_df[[channel_product_id_column, distribution_status_column]].to_excel(unpublished_output, index=False)
    print(f"✅ 已导出未铺货商品：{unpublished_output}")

    # 导出价格未设置商品
    if price_status_column in df.columns:
        missing_price_df = df[df[price_status_column] == "未设置"].copy()
        if not missing_price_df.empty:
            price_map_full = fetch_price_map(missing_price_df["商品编码"].dropna().unique().tolist())
            missing_price_df["价格"] = missing_price_df["商品编码"].apply(lambda c: price_map_full.get(c, ""))
            out_df = missing_price_df[[channel_product_id_column, "商品编码", "价格"]].drop_duplicates(subset=["商品编码"])
            out_df[channel_product_id_column] = out_df[channel_product_id_column].astype(str)
            missing_output = rf"{output_dir}\products_missing_price_{timestamp}.xlsx"
            out_df.to_excel(missing_output, index=False)
            print(f"⚠️ 已导出价格未设置商品：{missing_output}")
        else:
            print("✅ 所有商品都已设置价格，无需导出缺价表。")

    # ✅ 更新数据库 is_published 状态
    try:
        all_codes = df["商品编码"].dropna().unique().tolist()
        if all_codes:
            conn = psycopg2.connect(**PGSQL_CONFIG)
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE {TABLE_NAME}
                SET is_published = TRUE
                WHERE product_name = ANY(%s)
            """, (all_codes,))
            conn.commit()
            conn.close()
            print(f"📌 已更新数据库中 {len(all_codes)} 个商品编码的发布状态。")
        else:
            print("⚠️ 无有效商品编码，无需更新数据库发布状态。")
    except Exception as e:
        print(f"❌ 数据库 is_published 更新失败: {e}")

if __name__ == "__main__":
    main()
