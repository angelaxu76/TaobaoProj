import os
import psycopg2
import pandas as pd
from pathlib import Path
from config import BRAND_CONFIG

def mark_offline_products(brand_name: str):
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_CONFIG[brand_name]
    txt_dir: Path = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    output_dir: Path = config["OUTPUT_DIR"]

    # 1. 当前存在的商品编码（TXT 中的）
    txt_codes = set(f.stem for f in txt_dir.glob("*.txt"))

    # 2. 查询数据库中所有编码
    conn = psycopg2.connect(**pg_config)
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT product_code FROM {table_name}")
    db_codes = set(row[0] for row in cur.fetchall())

    # 3. 第一类：数据库中存在但 TXT 中缺失的编码（官网已下架）
    offline_by_missing = db_codes - txt_codes

    # 4. 第二类：有货尺码数量 < 2 的编码
    cur.execute(f"""
        SELECT product_code
        FROM {table_name}
        WHERE stock_status = '有货'
        GROUP BY product_code
        HAVING COUNT(DISTINCT size) < 2
    """)
    offline_by_low_stock = set(row[0] for row in cur.fetchall())

    cur.close()
    conn.close()

    # 5. 合并两类“即将下架”商品
    all_offline = sorted(offline_by_missing.union(offline_by_low_stock))

    if not all_offline:
        print(f"✅ {brand_name} 没有发现需要下架的商品。")
        return

    # 6. 输出 Excel
    df = pd.DataFrame({"下架商品编码": all_offline})
    output_file = output_dir / "offline_products.xlsx"
    df.to_excel(output_file, index=False)
    print(f"📦 {brand_name} 下架商品数: {len(all_offline)}，已导出到 {output_file}")

    # 7. 输出 TXT
    txt_file = output_dir / "offline_products.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        for code in all_offline:
            f.write(code + "\n")
    print(f"📝 同步导出 TXT 文件: {txt_file}")

if __name__ == "__main__":
    mark_offline_products("clarks")
