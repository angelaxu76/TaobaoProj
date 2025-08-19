# -*- coding: utf-8 -*-
"""
读取 BARBOUR["OUTPUT_DIR"]/price_mapping.xlsx（至少两列：color_code, jingya_id），
到 PostgreSQL 的 offers 表为每个 color_code 计算「可下单均价(GBP)」，
再用 calculate_jingya_prices 计算鲸芽价与淘宝零售价（RMB），
结果导出到 BARBOUR["OUTPUT_DIR"]/barbour_price_quote.xlsx。

列名容错：
- color_code：也接受 商品编码 / code / colorcode
- jingya_id：也接受 鲸芽id / 渠道id / channel_id / jingyaid
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2

# ==== 项目配置 ====
from config import BARBOUR
from common_taobao.core.price_utils import calculate_jingya_prices  # 已上传的文件

OUTPUT_DIR: Path = BARBOUR["OUTPUT_DIR"]
PGSQL = BARBOUR["PGSQL_CONFIG"]

# 默认输入/输出文件（都在 OUTPUT_DIR）
DEFAULT_INFILE = OUTPUT_DIR / "price_mapping.xlsx"
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
    # 将不同写法的列名统一到标准名
    alias = {c.lower().strip(): c for c in df.columns}
    cc = next((alias[k] for k in alias if k in ("color_code", "商品编码", "code", "colorcode")), None)
    jid = next((alias[k] for k in alias if k in ("jingya_id", "鲸芽id", "channel_id", "渠道id", "jingyaid")), None)
    if not cc or not jid:
        raise ValueError("输入 Excel 需包含列：color_code 与 jingya_id（不区分大小写，也可用同义列名）。")
    df = df.rename(columns={cc: "color_code", jid: "jingya_id"})
    df["color_code"] = df["color_code"].astype(str).str.strip()
    df["jingya_id"] = df["jingya_id"].astype(str).str.strip()
    df = df[df["color_code"] != ""]
    df = df.drop_duplicates(subset=["color_code", "jingya_id"])
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
            code = r["商品编码"]
            jid = r["渠道产品id"]
            note = ""
            try:
                avg_gbp = fetch_avg_price(conn, code)
                if avg_gbp is None:
                    note = "未找到价格记录"
                    untaxed = retail = None
                else:
                    # 使用你项目中的计算函数（含低价补差/运费/汇率逻辑）
                    untaxed, retail = calculate_jingya_prices(avg_gbp)  # 可传 delivery_cost / exchange_rate 覆盖
                rows.append({
                    "商品编码": code,
                    "渠道产品id": jid,
                    "avg_price_gbp": avg_gbp,
                    "untaxed_rmb": untaxed,
                    "retail_rmb": retail,
                    "notes": note
                })
            except Exception as e:
                rows.append({
                    "商品编码": code,
                    "渠道产品id": jid,
                    "avg_price_gbp": None,
                    "untaxed_rmb": None,
                    "retail_rmb": None,
                    "notes": f"异常: {e}"
                })
    finally:
        conn.close()

    df_out = pd.DataFrame(rows, columns=[
        "商品编码", "渠道产品id", "avg_price_gbp", "untaxed_rmb", "retail_rmb", "notes"
    ])

    outfile.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(outfile, engine="openpyxl") as writer:
        meta = pd.DataFrame({
            "生成时间": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "输入文件": [str(infile)],
            "数据库": [PGSQL.get("dbname")]
        })
        df_out.to_excel(writer, index=False, sheet_name="prices")
        meta.to_excel(writer, index=False, sheet_name="meta")

    print(f"✅ 已完成：{outfile}")


