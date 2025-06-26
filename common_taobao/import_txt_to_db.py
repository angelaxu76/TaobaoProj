import os
import re
import psycopg2
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import BRAND_CONFIG
from common_taobao.txt_parser import parse_txt_to_record
from psycopg2.extensions import adapt

DEBUG = True  # 全局调试开关


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
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    cfg          = BRAND_CONFIG[brand_name]
    TXT_DIR      = cfg["TXT_DIR"]
    PGSQL        = cfg["PGSQL_CONFIG"]
    TABLE_NAME   = cfg["TABLE_NAME"]
    STORE_DIR    = cfg["STORE_DIR"]

    conn = psycopg2.connect(**PGSQL)
    cur = conn.cursor()

    if brand_name == "camper":
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                product_code, product_name, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                stock_name, last_checked, is_published, ean
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_code, size, stock_name)
            DO UPDATE SET
                stock_status        = EXCLUDED.stock_status,
                discount_price_gbp  = EXCLUDED.discount_price_gbp,
                original_price_gbp  = EXCLUDED.original_price_gbp,
                skuid               = EXCLUDED.skuid,
                last_checked        = EXCLUDED.last_checked,
                is_published        = EXCLUDED.is_published,
                ean                 = EXCLUDED.ean;
        """
    else:
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                product_code, product_name, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                stock_name, last_checked, is_published
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_code, size, stock_name)
            DO UPDATE SET
                stock_status        = EXCLUDED.stock_status,
                discount_price_gbp  = EXCLUDED.discount_price_gbp,
                original_price_gbp  = EXCLUDED.original_price_gbp,
                skuid               = EXCLUDED.skuid,
                last_checked        = EXCLUDED.last_checked,
                is_published        = EXCLUDED.is_published;
        """

    txt_files = list(TXT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"⚠️ 没有 TXT 文件在目录 {TXT_DIR}")
        return

    for store_folder in STORE_DIR.iterdir():
        if not store_folder.is_dir() or store_folder.name == "clarks_default":
            continue

        stock_name = store_folder.name
        print(f"\n🔄 处理店铺: {stock_name}")
        sku_map = load_sku_mapping_from_store(store_folder)
        print(f"🔢 映射表共 {len(sku_map)} 条")

        for txt_file in txt_files:
            try:
                records = parse_txt_to_record(txt_file, brand_name)
                if not records:
                    print(f"⚠️ 无数据: {txt_file.name}")
                    continue

                inserted = 0
                for rec in records:
                    if brand_name == "camper":
                        (product_name, url, size, gender,
                         stock_status, ori_price, dis_price, _, ean) = rec
                    else:
                        (product_name, url, size, gender,
                         stock_status, ori_price, dis_price, _) = rec
                        ean = None

                    # 提取商品编码（8位数字）
                    match = re.search(r"\b(\d{8})\b", product_name)
                    product_code = match.group(1) if match else product_name.strip()

                    spec_key = f"{product_code},{size}"
                    skuid = sku_map.get(spec_key)
                    is_published = bool(skuid)

                    if DEBUG:
                        print(
                            f"{'🔑' if skuid else '⚠️'} {spec_key:<18} "
                            f"| stock_status={stock_status:<4} "
                            f"| skuid={skuid or 'N/A':<12} "
                            f"| is_published={is_published} "
                            f"| ean={ean or '-'}"
                        )

                    full_rec = (
                        product_code, product_name.strip(), url, size.strip(), gender.strip(),
                        skuid or "", stock_status.strip(), ori_price, dis_price,
                        stock_name.strip(), datetime.now(), is_published
                    )
                    if brand_name == "camper":
                        full_rec += (ean,)

                    if DEBUG:
                        adapted = [adapt(x).getquoted().decode() if x is not None else 'NULL' for x in full_rec]
                        print("📝 SQL:", insert_sql.strip().replace('\n', ' '))
                        print("📦 PARAMS:", full_rec)
                        # print("🧪 FINAL SQL:", insert_sql % tuple(adapted))  # 开启可调试用

                    cur.execute(insert_sql, full_rec)
                    inserted += 1

                print(f"✅ 已导入: {txt_file.name}（{inserted} 条） → 店铺: {stock_name}")
            except Exception as e:
                print(f"❌ 错误文件: {txt_file.name} - {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n✅ 品牌 [{brand_name}] 的 TXT 数据已全部导入数据库。")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("用法: python import_txt_to_db.py <brand>")
    else:
        import_txt_to_db(sys.argv[1])
