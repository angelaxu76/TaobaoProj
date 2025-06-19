
import os
import shutil
import psycopg2
import pandas as pd
from config import PGSQL_CONFIG
from common_taobao.classifier import classify_product

def prepare_products_for_publication(brand_config, brand_type="shoes"):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cursor = conn.cursor()

    txt_dir = brand_config["TXT_DIR"]
    output_dir = brand_config["OUTPUT_DIR"]

    # 清空输出目录
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cursor.execute(f"""
        SELECT DISTINCT product_name, gender, product_url
        FROM {brand_config['TABLE_NAME']}
        WHERE is_published = FALSE
    """)

    rows = cursor.fetchall()
    product_map = {}

    for product_name, gender, url in rows:
        txt_file = txt_dir / f"{product_name}.txt"
        if not txt_file.exists():
            continue

        with open(txt_file, "r", encoding="utf-8") as f:
            content = f.read()
        text = content.lower()

        category = classify_product(text, brand_type=brand_type)
        key = (gender or "unknown", category)
        product_map.setdefault(key, []).append(product_name)

    for (gender, category), codes in product_map.items():
        subdir = output_dir / gender / category
        subdir.mkdir(parents=True, exist_ok=True)
        for code in codes:
            src = txt_dir / f"{code}.txt"
            dst = subdir / f"{code}.txt"
            shutil.copyfile(src, dst)

    print(f"✅ 准备完成，共生成 {sum(len(v) for v in product_map.values())} 个商品发布文件")
