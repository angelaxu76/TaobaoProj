import pandas as pd
import psycopg2
from pathlib import Path

def get_publishable_codes_for_supplier(config: dict) -> list:
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    txt_dir = Path(config["TXT_DIR"])

    # 1. 数据库层面筛选：未发布、男女款、有货尺码 ≥4、总库存 >30
    query = f"""
        SELECT product_code
        FROM {table}
        WHERE gender IN ('男款', '女款')
          AND is_published = FALSE
          AND stock_count > 0
        GROUP BY product_code
        HAVING COUNT(DISTINCT size) >= 4
           AND SUM(stock_count) > 30
    """
    df = pd.read_sql(query, conn)
    conn.close()
    candidate_codes = df["product_code"].unique().tolist()

    # 2. TXT 文件校验：至少有 4 个 ":有货"
    def txt_has_4_sizes(code: str) -> bool:
        txt_path = txt_dir / f"{code}.txt"
        if not txt_path.exists():
            return False
        try:
            lines = txt_path.read_text(encoding="utf-8").splitlines()
            size_line = next((line for line in lines if line.startswith("Product Size:")), "")
            return size_line.count(":有货") >= 4
        except:
            return False

    valid_codes = [code for code in candidate_codes if txt_has_4_sizes(code)]

    print(f"🟢 Camper 供货商模式下可发布商品数量：{len(valid_codes)}")
    return valid_codes
