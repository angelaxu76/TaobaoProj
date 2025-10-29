
import psycopg2
from pathlib import Path

# === 参数配置 ===
PGSQL_CONFIG = {
    "host": "192.168.5.9",
    "port": 5432,
    "user": "postgres",
    "password": "516518",  # 请根据实际情况替换
    "dbname": "taobao_inventory_db"
}
TABLE_NAME = "clarks_inventory"
STORE_NAME = "五小剑"
TXT_DIR = Path("D:/TB/Products/clarks/publication/TXT")

# === 查询当前店铺未发布的商品编码（同一编码不能在当前店铺已发布） ===
def get_unpublished_codes():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT product_code
        FROM {TABLE_NAME}
        WHERE stock_name = %s AND is_published = FALSE
        GROUP BY product_code
        HAVING COUNT(*) = COUNT(*)  -- 保证 GROUP BY 生效
          AND product_code NOT IN (
              SELECT DISTINCT product_code FROM {TABLE_NAME}
              WHERE stock_name = %s AND is_published = TRUE
          )
    """, (STORE_NAME, STORE_NAME))
    result = [row[0] for row in cursor.fetchall()]
    conn.close()
    return result

# === 判断是否有 >= 3 个“有货”尺码 ===
def has_3_or_more_instock_sizes(code):
    txt_path = TXT_DIR / f"{code}.txt"
    if not txt_path.exists():
        return False
    try:
        lines = txt_path.read_text(encoding="utf-8").splitlines()
        size_line = next((line for line in lines if line.startswith("Product Size:")), "")
        count = size_line.count(":有货")
        return count >= 3
    except Exception as e:
        print(f"❌ 处理 {code} 失败: {e}")
        return False

# === 主程序 ===
if __name__ == "__main__":
    all_codes = get_unpublished_codes()
    print(f"🟡 当前店铺未发布商品编码: {len(all_codes)} 个")

    valid_codes = [code for code in all_codes if has_3_or_more_instock_sizes(code)]
    print(f"✅ 有效商品（≥3个尺码有货）数量: {len(valid_codes)}")
    print("📋 编码预览（前20条）:", valid_codes[:20])
