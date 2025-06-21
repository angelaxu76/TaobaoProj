
import os
import psycopg2
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import CLARKS, ECCO, GEOX
from common_taobao.txt_parser import parse_txt_to_record

BRAND_MAP = {
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def load_sku_mapping_from_store(store_path: Path):
    sku_map = {}
    for file in store_path.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        print(f"📂 读取映射文件: {file.name}")
        df = pd.read_excel(file, dtype=str)
        for _, row in df.iterrows():
            spec = str(row.get("sku规格", "")).replace("，", ",").strip().rstrip(",")
            skuid = str(row.get("skuID", "")).strip()
            if spec and skuid:
                sku_map[spec] = skuid
    return sku_map

def import_txt_to_db(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
    TXT_DIR = config["TXT_DIR"]
    PGSQL = config["PGSQL_CONFIG"]
    TABLE_NAME = config["TABLE_NAME"]
    STORE_DIR = config["STORE_DIR"]

    conn = psycopg2.connect(**PGSQL)
    cur = conn.cursor()

    insert_sql = f"""
        INSERT INTO {TABLE_NAME} (
            product_name, product_url, size, gender, skuid,
            stock_status, original_price_gbp, discount_price_gbp,
            stock_name, last_checked, is_published
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (product_name, size, stock_name)
        DO UPDATE SET
            stock_status = EXCLUDED.stock_status,
            discount_price_gbp = EXCLUDED.discount_price_gbp,
            original_price_gbp = EXCLUDED.original_price_gbp,
            skuid = EXCLUDED.skuid,
            last_checked = EXCLUDED.last_checked,
            is_published = EXCLUDED.is_published;
    """

    txt_files = list(TXT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"⚠️ 没有 TXT 文件在目录 {TXT_DIR}")
        return

    for store_folder in STORE_DIR.iterdir():
        if not store_folder.is_dir() or store_folder.name == "clarks_default":
            continue
        stock_name = store_folder.name
        print(f"🔄 处理店铺: {stock_name}")

        sku_map = load_sku_mapping_from_store(store_folder)
        print(f"🔢 映射表共 {len(sku_map)} 条")

        for file in txt_files:
            try:
                records = parse_txt_to_record(file)
                if not records:
                    print(f"⚠️ 无数据: {file.name}")
                    continue

                inserted = 0
                for r in records:
                    product_name, url, size, gender, product_code, stock_status, ori_price, dis_price, _ = r
                    spec_key = f"{product_code},{size}"
                    skuid = sku_map.get(spec_key)
                    is_published = skuid is not None
                    if not skuid:
                        print(f"⚠️ 未匹配 SKU: {spec_key}")
                    else:
                        print(f"🔑 匹配成功: {spec_key} → SKU ID: {skuid}")

                    full_record = (
                        product_name, url, size, gender, skuid,
                        stock_status, ori_price, dis_price,
                        stock_name, datetime.now(), is_published
                    )
                    print(f"🧪 DEBUG: 商品编码={product_code} | SKU={skuid} | 是否发布={is_published}")
                    cur.execute(insert_sql, full_record)
                    inserted += 1

                print(f"✅ 已导入: {file.name}（{inserted} 条） → 店铺: {stock_name}")
            except Exception as e:
                print(f"❌ 错误文件: {file.name} - {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ 品牌 [{brand_name}] 的 TXT 数据已全部导入数据库。")
