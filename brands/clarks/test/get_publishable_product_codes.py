
import psycopg2
import pandas as pd

def get_publishable_product_codes(config: dict, store_name: str) -> list:
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table_name = config["TABLE_NAME"]
    txt_dir = config["TXT_DIR"]

    # ✅ 只选取“所有尺码都未发布”的商品编码
    query = f"""
        SELECT product_name
        FROM {table_name}
        WHERE stock_name = %s
        GROUP BY product_name
        HAVING SUM(CASE WHEN is_published THEN 1 ELSE 0 END) = 0
    """
    df = pd.read_sql(query, conn, params=(store_name,))
    codes = df["product_name"].unique().tolist()

    def valid_stock(code):
        txt_path = txt_dir / f"{code}.txt"
        if not txt_path.exists():
            return False
        try:
            content = txt_path.read_text(encoding="utf-8")
            stock_line = next((line for line in content.splitlines() if "Size Stock (EU):" in line), "")
            sizes = [s for s in stock_line.replace("Size Stock (EU):", "").split(";") if ":有货" in s]
            return len(sizes) >= 3
        except Exception:
            return False

    return [code for code in codes if valid_stock(code)]
