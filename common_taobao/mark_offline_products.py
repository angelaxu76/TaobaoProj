import os
import psycopg2
import pandas as pd
from pathlib import Path
from config import CLARKS, CAMPER, ECCO, GEOX, BRAND_CONFIG  # 其他品牌配置按需导入

# 所有品牌配置集合（支持动态传入 brand 名称）

def mark_offline_products(brand_name: str):
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_CONFIG[brand_name]
    txt_dir: Path = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    output_dir: Path = config["OUTPUT_DIR"]

    # 1. 获取 TXT 文件中的所有编码
    txt_codes = set(f.stem for f in txt_dir.glob("*.txt"))

    # 2. 查询数据库中所有商品编码
    conn = psycopg2.connect(**pg_config)
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT product_name FROM {table_name}")
    db_codes = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()

    # 3. 差集：数据库中有，TXT 中没有 = 下架
    offline_codes = sorted(db_codes - txt_codes)

    if not offline_codes:
        print(f"✅ {brand_name} 没有发现下架商品。")
        return

    # 4. 输出为 Excel
    df = pd.DataFrame({"下架商品编码": offline_codes})
    output_file = output_dir / "offline_products.xlsx"
    df.to_excel(output_file, index=False)
    print(f"📦 {brand_name} 下架商品数: {len(offline_codes)}，已导出到 {output_file}")

    # 5. 可选：输出为 TXT
    txt_file = output_dir / "offline_products.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        for code in offline_codes:
            f.write(code + "\n")
    print(f"📝 同步导出 TXT 文件: {txt_file}")

if __name__ == "__main__":
    mark_offline_products("clarks")  # 可改成其他品牌
