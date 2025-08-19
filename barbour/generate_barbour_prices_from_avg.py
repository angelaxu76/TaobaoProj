# -*- coding: utf-8 -*-
"""
读取 BARBOUR["OUTPUT_DIR"]/channel_products.xlsx（至少两列：商品编码, 渠道产品ID），
到 PostgreSQL 的 offers 表为每个【商品编码】计算「可下单均价(GBP)」，
再用 calculate_jingya_prices 计算鲸芽价与淘宝零售价（RMB），
结果导出到 BARBOUR["OUTPUT_DIR"]/barbour_price_quote.xlsx。

列名容错：
- 商品编码：也接受 商品编码 / code / colorcode
- 渠道产品ID：也接受 渠道产品ID / 渠道id / channel_id / jingyaid
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2

# ==== 项目配置 ====
from config import BARBOUR
# 允许两种来源：common_taobao 或本地 price_utils，谁能导入就用谁
try:
    from common_taobao.core.price_utils import calculate_jingya_prices
except Exception:
    from price_utils import calculate_jingya_prices  # 兜底

OUTPUT_DIR: Path = BARBOUR["OUTPUT_DIR"]
PGSQL = BARBOUR["PGSQL_CONFIG"]

# 默认输入/输出文件（都在 OUTPUT_DIR）
DEFAULT_INFILE = OUTPUT_DIR / "channel_products.xlsx"
DEFAULT_OUTFILE = OUTPUT_DIR / "barbour_price_quote.xlsx"

SQL_AVG_STRICT = """
SELECT AVG(price_gbp)::numeric(10,2) AS avg_price
FROM offers
WHERE color_code = %s
  AND can_order = TRUE
  AND (stock_status IS NULL OR LOWER(stock_status) = 'in stock' OR stock_status = '有货')
"""

SQL_AVG_RELAX = """
SELECT AVG(price_gbp)::numeric(10,2) AS avg_price
FROM offers
WHERE color_code = %s
"""

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 将不同写法的列名统一到标准名（商品编码 / 渠道产品ID）
    alias = {c.lower().strip(): c for c in df.columns}
    cc = next((alias[k] for k in alias if k in ("商品编码", "code", "colorcode")), None)
    jid = next((alias[k] for k in alias if k in ("渠道产品id", "渠道id", "channel_id", "jingyaid", "渠道产品ID")), None)
    if not cc or not jid:
        raise ValueError("输入 Excel 需包含列：商品编码 与 渠道产品ID（不区分大小写，也可用同义列名）。")
    df = df.rename(columns={cc: "商品编码", jid: "渠道产品ID"})
    df["商品编码"] = df["商品编码"].astype(str).str.strip()
    df["渠道产品ID"] = df["渠道产品ID"].astype(str).str.strip()
    df = df[df["商品编码"] != ""]
    df = df.drop_duplicates(subset=["商品编码", "渠道产品ID"])
    return df

def fetch_avg_price(conn, color_code: str):
    with conn.cursor() as cur:
        # 优先取「可下单」均价
        cur.execute(SQL_AVG_STRICT, (color_code,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        # 若没有，则退化为全部记录的均价
        cur.execute(SQL_AVG_RELAX, (color_code,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    return None

def generate_price_for_jingya_publication(infile: Path = DEFAULT_INFILE, outfile: Path = DEFAULT_OUTFILE):
    if not infile.exists():
        print(f"❌ 找不到输入文件：{infile}")
        sys.exit(1)

    df_in = pd.read_excel(infile)
    df_in = normalize_columns(df_in)

    try:
        conn = psycopg2.connect(**PGSQL)
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        sys.exit(1)

    rows = []
    try:
        for _, r in df_in.iterrows():
            code = r["商品编码"]          # -> offers.color_code
            jid = r["渠道产品ID"]
            note = ""
            try:
                avg_gbp = fetch_avg_price(conn, code)
                if avg_gbp is None:
                    note = "未找到价格记录"
                    untaxed = retail = None
                else:
                    # 使用你的价格计算（可按需传 delivery_cost / exchange_rate 调整）
                    untaxed, retail = calculate_jingya_prices(avg_gbp)
                rows.append({
                    "商品编码": code,
                    "渠道产品ID": jid,
                    "avg_price_gbp": avg_gbp,
                    "未税价格": untaxed,
                    "零售价": retail,
                    "notes": note
                })
            except Exception as e:
                rows.append({
                    "商品编码": code,
                    "渠道产品ID": jid,
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
        meta = pd.DataFrame({
            "生成时间": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "输入文件": [str(infile)],
            "数据库": [PGSQL.get("dbname")]
        })
        df_out.to_excel(writer, index=False, sheet_name="Sheet1")

    print(f"✅ 已完成：{outfile}")

if __name__ == "__main__":
    # 支持命令行可选自定义文件名（仍限定在 OUTPUT_DIR 下）
    in_arg = sys.argv[1] if len(sys.argv) > 1 else None
    out_arg = sys.argv[2] if len(sys.argv) > 2 else None
    in_file = OUTPUT_DIR / in_arg if in_arg else DEFAULT_INFILE
    out_file = OUTPUT_DIR / out_arg if out_arg else DEFAULT_OUTFILE
    generate_price_for_jingya_publication(in_file, out_file)
