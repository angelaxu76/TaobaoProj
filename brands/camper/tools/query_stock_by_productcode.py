import psycopg2
import pandas as pd
from pathlib import Path
from config import CAMPER  # 确保你的 config 中有 CAMPER 配置项

# === 配置路径 ===
QUERY_FILE = Path(r"D:\TB\Products\camper\repulibcation\queryID.txt")
OUTPUT_FILE = Path(r"D:\TB\Products\camper\repulibcation\queryID.xlsx")

# === 读取商品编码列表 ===
with open(QUERY_FILE, "r", encoding="utf-8") as f:
    product_codes = [line.strip() for line in f if line.strip()]

if not product_codes:
    raise ValueError("❌ queryID.txt 中没有有效的商品编码")

# === 数据库连接 ===
pg_config = CAMPER["PGSQL_CONFIG"]
table_name = CAMPER["TABLE_NAME"]

conn = psycopg2.connect(**pg_config)

# === 查询总库存（按 product_code 分组汇总所有尺码）===
query = f"""
    SELECT product_code, SUM(stock_count) AS total_stock
    FROM {table_name}
    WHERE product_code = ANY(%s)
    GROUP BY product_code
    ORDER BY product_code;
"""

df = pd.read_sql_query(query, conn, params=(product_codes,))
conn.close()

# === 补全未找到的编码（库存为0） ===
found_codes = set(df["product_code"])
missing_codes = [code for code in product_codes if code not in found_codes]
if missing_codes:
    df_missing = pd.DataFrame({"product_code": missing_codes, "total_stock": [0] * len(missing_codes)})
    df = pd.concat([df, df_missing], ignore_index=True)

# === 排序并写入 Excel ===
df = df.sort_values(by="product_code").rename(columns={
    "product_code": "商品编码",
    "total_stock": "总库存"
})
df.to_excel(OUTPUT_FILE, index=False)
print(f"✅ 查询完成，结果已保存到: {OUTPUT_FILE}")
