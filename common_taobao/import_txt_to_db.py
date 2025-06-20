import psycopg2
from config import CLARKS, ECCO, GEOX
from common_taobao.txt_parser import parse_txt_to_record

BRAND_MAP = {
    "clarks": CLARKS,
    "ecco": ECCO,
    "geox": GEOX
}

def import_txt_to_db(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_MAP:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_MAP[brand_name]
    TXT_DIR = config["TXT_DIR"]
    PGSQL = config["PGSQL_CONFIG"]
    TABLE_NAME = config["TABLE_NAME"]

    conn = psycopg2.connect(**PGSQL)
    cur = conn.cursor()

    insert_sql = f"""
        INSERT INTO {TABLE_NAME} (
            product_name, product_url, size, gender, skuid,
            stock_status, original_price_gbp, discount_price_gbp,
            stock_name, is_published
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false)
        ON CONFLICT (product_name, size, stock_name)
        DO UPDATE SET
            stock_status = EXCLUDED.stock_status,
            discount_price_gbp = EXCLUDED.discount_price_gbp,
            last_checked = CURRENT_TIMESTAMP;
    """

    txt_files = list(TXT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"⚠️ 没有 TXT 文件在目录 {TXT_DIR}")
        return

    for file in txt_files:
        try:
            records = parse_txt_to_record(file)
            if not records:
                print(f"⚠️ 无数据: {file.name}")
                continue
            for record in records:
                cur.execute(insert_sql, record)
            print(f"✅ 已导入: {file.name}（{len(records)} 条）")
        except Exception as e:
            print(f"❌ 错误文件: {file.name} - {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n✅ 品牌 [{brand_name}] 的 TXT 数据已全部导入数据库。")