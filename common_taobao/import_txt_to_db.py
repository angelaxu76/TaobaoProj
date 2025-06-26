import os
import psycopg2
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import BRAND_CONFIG
from common_taobao.txt_parser import parse_txt_to_record


def load_sku_mapping_from_store(store_path: Path):
    """读取店铺 Excel，返回 {product_code,size -> skuid} 字典"""
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
    cur  = conn.cursor()

    # Camper 额外多一个 ean 字段
    if brand_name == "camper":
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                product_name, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                stock_name, last_checked, is_published, ean
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_name, size, stock_name)
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
                product_name, product_url, size, gender, skuid,
                stock_status, original_price_gbp, discount_price_gbp,
                stock_name, last_checked, is_published
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_name, size, stock_name)
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
                        (product_name, url, size, gender, product_code,
                         stock_status, ori_price, dis_price, _, ean) = rec
                    else:
                        (product_name, url, size, gender, product_code,
                         stock_status, ori_price, dis_price, _) = rec
                        ean = None  # 非 Camper 占位

                    spec_key = f"{product_code},{size}"
                    skuid = sku_map.get(spec_key)          # 若无匹配返回 None
                    is_published = bool(skuid)

                    # 📝 统一 DEBUG 输出
                    print(
                        f"{'🔑' if skuid else '⚠️'} "
                        f"{spec_key:<18} | skuid={skuid or 'N/A':<12} "
                        f"| is_published={is_published}"
                    )

                    full_rec = (
                        product_name, url, size, gender, skuid or "",
                        stock_status, ori_price, dis_price,
                        stock_name, datetime.now(), is_published
                    )
                    if brand_name == "camper":
                        full_rec += (ean,)

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
    # 例：python import_txt_to_db.py clarks
    import sys
    if len(sys.argv) != 2:
        print("用法: python import_txt_to_db.py <brand>")
    else:
        import_txt_to_db(sys.argv[1])
