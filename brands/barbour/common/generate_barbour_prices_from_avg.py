# -*- coding: utf-8 -*-
"""
从 D:/TB/Products/barbour/repulibcation/codes.txt 读取商品编码，
到 PostgreSQL 的 barbour_offers 表为每个【商品编码】计算「可下单均价(GBP)」，
再用 calculate_jingya_prices 计算鲸芽价与淘宝零售价（RMB），
并从 barbour_inventory 表获取渠道产品ID（channel_product_id），
结果导出到 BARBOUR["OUTPUT_DIR"]/barbour_price_quote.xlsx。

说明（基于新表结构）：
- 均价来源：barbour_offers.sale_price_gbp（生成列 = COALESCE(price_gbp, original_price_gbp)）
- 可下单判断：is_active = TRUE 且 stock_count > 0
"""
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2

# ==== 项目配置 ====
from config import BARBOUR
try:
    from common_taobao.core.price_utils import calculate_jingya_prices
except Exception:
    from common_taobao.core.price_utils import calculate_jingya_prices  # 兜底

OUTPUT_DIR: Path = BARBOUR["OUTPUT_DIR"]
PGSQL = BARBOUR["PGSQL_CONFIG"]

CODES_FILE = Path(r"D:\TB\Products\barbour\repulibcation\codes.txt")
DEFAULT_OUTFILE = OUTPUT_DIR / "barbour_price_quote.xlsx"

# ——— 新库：用 barbour_offers + sale_price_gbp + is_active/stock_count ———
SQL_AVG_STRICT = """
SELECT AVG(sale_price_gbp)::numeric(10,2) AS avg_price
FROM barbour_offers
WHERE product_code = %s
  AND is_active = TRUE
  AND COALESCE(stock_count, 0) > 0
"""

SQL_AVG_RELAX = """
SELECT AVG(sale_price_gbp)::numeric(10,2) AS avg_price
FROM barbour_offers
WHERE product_code = %s
  AND is_active = TRUE
"""

SQL_CHANNEL_ID = """
SELECT string_agg(DISTINCT channel_product_id::text, ',') AS channel_ids
FROM barbour_inventory
WHERE product_code = %s
  AND channel_product_id IS NOT NULL
  AND channel_product_id <> ''
"""

def fetch_avg_price(conn, product_code: str):
    with conn.cursor() as cur:
        cur.execute(SQL_AVG_STRICT, (product_code,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        cur.execute(SQL_AVG_RELAX, (product_code,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    return None

def fetch_channel_product_id(conn, product_code: str) -> str | None:
    """从 barbour_inventory 中按 product_code 匹配，返回去重后的渠道产品ID（逗号拼接）。"""
    with conn.cursor() as cur:
        cur.execute(SQL_CHANNEL_ID, (product_code,))
        row = cur.fetchone()
        if row:
            return row[0]  # 可能是 None 或 'id1,id2'
    return None

def generate_price_for_jingya_publication(outfile: Path = DEFAULT_OUTFILE):
    if not CODES_FILE.exists():
        print(f"❌ 找不到 codes.txt：{CODES_FILE}")
        sys.exit(1)

    # 读取商品编码
    codes = []
    with open(CODES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            code = line.strip()
            if code:
                codes.append(code)

    try:
        conn = psycopg2.connect(**PGSQL)
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        sys.exit(1)

    rows = []
    try:
        for code in codes:
            note = ""
            try:
                channel_id = fetch_channel_product_id(conn, code)
                avg_gbp = fetch_avg_price(conn, code)

                if avg_gbp is None:
                    note = "未找到价格记录"
                    untaxed = retail = None
                else:
                    untaxed, retail = calculate_jingya_prices(avg_gbp)

                if not channel_id:
                    note = (note + "；" if note else "") + "无渠道产品ID"

                rows.append({
                    "商品编码": code,
                    "渠道产品ID": channel_id,
                    "avg_price_gbp": avg_gbp,
                    "未税价格": untaxed,
                    "零售价": retail,
                    "notes": note
                })
            except Exception as e:
                rows.append({
                    "商品编码": code,
                    "渠道产品ID": None,
                    "avg_price_gbp": None,
                    "未税价格": None,
                    "零售价": None,
                    "notes": f"异常: {e}"
                })
    finally:
        conn.close()

    df_out = pd.DataFrame(rows, columns=[
        "商品编码", "渠道产品ID", "avg_price_gbp", "未税价格", "零售价", "notes"
    ])

    outfile.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(outfile, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Sheet1")
        # 这里原来准备写 meta sheet，但没写入；保持一致即可。
    print(f"✅ 已完成：{outfile}")

if __name__ == "__main__":
    out_arg = sys.argv[1] if len(sys.argv) > 1 else None
    out_file = OUTPUT_DIR / out_arg if out_arg else DEFAULT_OUTFILE
    generate_price_for_jingya_publication(out_file)
