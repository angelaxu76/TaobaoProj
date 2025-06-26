import re
import psycopg2
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import BRAND_CONFIG
from common_taobao.txt_parser import parse_txt_to_record

DEBUG = True  # 调试完可改为 False


def load_sku_mapping_from_store(store_path: Path) -> dict:
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
    cfg = BRAND_CONFIG[brand_name]

    TXT_DIR, PGSQL, TABLE, STORE_DIR = (
        cfg["TXT_DIR"], cfg["PGSQL_CONFIG"], cfg["TABLE_NAME"], cfg["STORE_DIR"]
    )

    conn = psycopg2.connect(**PGSQL)
    cur = conn.cursor()

    insert_sql = f"""
        INSERT INTO {TABLE} (
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

    for store in STORE_DIR.iterdir():
        if not store.is_dir():
            continue
        stock_name = store.name
        print(f"\n🔄 处理店铺: {stock_name}")
        sku_map = load_sku_mapping_from_store(store)
        print(f"🔢 映射表共 {len(sku_map)} 条")

        for txt_file in TXT_DIR.glob("*.txt"):
            try:
                records = parse_txt_to_record(txt_file, brand_name)
                if not records:
                    continue

                for rec in records:
                    # 动态解包不同品牌结构
                    if len(rec) == 10:  # Camper
                        pname, url, size, gender, _, stock, oprice, dprice, _, _ = rec
                        product_name = extract_product_code(pname)
                    elif len(rec) == 9:  # Clarks / ECCO / GEOX
                        pname, url, size, gender, code_field, stock, oprice, dprice, _ = rec
                        product_name = code_field.strip() or extract_product_code(pname)
                    elif len(rec) == 8:  # 最早格式
                        pname, url, size, gender, stock, oprice, dprice, _ = rec
                        product_name = extract_product_code(pname)
                    else:
                        raise ValueError(f"未知字段数: {len(rec)}")

                    spec = f"{product_name},{size.strip()}"
                    skuid = sku_map.get(spec, "")
                    is_pub = bool(skuid)

                    row = (
                        product_name, url, size.strip(), gender.strip(),
                        skuid, stock.strip(), oprice, dprice,
                        stock_name, datetime.now(), is_pub
                    )

                    if DEBUG:
                        print(f"{'🔑' if skuid else '⚠️'} {product_name},{size} | stock={stock} | skuid={skuid or 'N/A'} | is_pub={is_pub}")
                        print("📦 PARAMS:", row)

                    cur.execute(insert_sql, row)

                print(f"✅ 已导入: {txt_file.name} → 店铺: {stock_name}")

            except Exception as e:
                print(f"❌ 错误文件: {txt_file.name} - {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n✅ 品牌 [{brand_name}] 的 TXT 数据已全部导入数据库。")


def extract_product_code(title: str) -> str:
    """从商品标题中提取 8 位编码"""
    match = re.search(r"\b(\d{8})\b", title)
    return match.group(1) if match else title.strip()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("用法: python import_txt_to_db.py <brand>")
    else:
        import_txt_to_db(sys.argv[1])
