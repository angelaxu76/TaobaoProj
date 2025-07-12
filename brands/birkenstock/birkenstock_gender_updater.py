import psycopg2
from config import BIRKENSTOCK

PGCONFIG = BIRKENSTOCK["PGSQL_CONFIG"]
TABLE = BIRKENSTOCK["TABLE_NAME"]

def classify_gender(sizes):
    has_36 = "36" in sizes
    has_45 = "45" in sizes
    if has_36 and has_45:
        return "男女同款"
    elif has_36:
        return "女款"
    elif has_45:
        return "男款"
    return "未知"

def update_gender():
    conn = psycopg2.connect(**PGCONFIG)
    cursor = conn.cursor()

    # ✅ 改为正确字段 product_code
    cursor.execute(f"SELECT DISTINCT product_code FROM {TABLE}")
    product_codes = [row[0] for row in cursor.fetchall()]
    print(f"🔍 共找到 {len(product_codes)} 个商品编码")

    updated = 0
    for code in product_codes:
        cursor.execute(f"SELECT size FROM {TABLE} WHERE product_code = %s", (code,))
        sizes = [row[0] for row in cursor.fetchall()]
        gender = classify_gender(sizes)
        cursor.execute(f"UPDATE {TABLE} SET gender = %s WHERE product_code = %s", (gender, code))
        updated += 1
        print(f"✅ {code}: {gender}")

    conn.commit()
    conn.close()
    print(f"🎉 共更新 {updated} 条 gender 字段")

if __name__ == "__main__":
    update_gender()
