# -*- coding: utf-8 -*-
"""
导出 Barbour 折扣候选为 Excel：
- 参数：min_discount（折扣率阈值，%）、min_sizes（最少有货尺码数）、code_like（编码模糊关键词，可空）
- 读取 config.BARBOUR 的 PGSQL_CONFIG 与 OUTPUT_DIR
- 返回生成的 .xlsx 文件路径
"""
from pathlib import Path
from datetime import datetime
import re
import psycopg2
import pandas as pd

from config import BARBOUR, ensure_all_dirs  # 确保 ensure_all_dirs 存在

SQL = """
SELECT
  o.product_code,
  p.style_name AS product_style_name,
  o.site_name,
  o.offer_url,
  MIN(o.price_gbp)::numeric(10,2)          AS price_gbp,
  MIN(o.original_price_gbp)::numeric(10,2) AS original_price,
  MAX(o.discount_pct)                      AS discount_pct,
  STRING_AGG(DISTINCT o.size, ',' ORDER BY o.size) AS sizes_in_stock,
  COUNT(DISTINCT o.size) FILTER (WHERE o.stock_count > 0) AS available_count
FROM barbour_offers o
LEFT JOIN barbour_products p
  ON o.product_code = p.product_code
WHERE o.product_code IS NOT NULL
  AND o.stock_count > 0
  AND o.discount_pct > %s
  AND (%s IS NULL OR o.product_code ILIKE %s)
GROUP BY o.product_code, p.style_name, o.site_name, o.offer_url
HAVING COUNT(DISTINCT o.size) > %s
ORDER BY discount_pct DESC, price_gbp ASC, o.product_code;
"""

def _sanitize(s: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", s or "")

def export_barbour_discounts_excel(min_discount: float, min_sizes: int, code_like: str | None = None) -> Path:
    """
    导出到 Excel 并返回文件路径
    """
    out_dir: Path = BARBOUR["PUBLICATION_DIR"]
    ensure_all_dirs(out_dir)

    kw_like = f"%{code_like}%" if code_like else None
    params = (min_discount, None if kw_like is None else kw_like, kw_like, min_sizes)

    with psycopg2.connect(**BARBOUR["PGSQL_CONFIG"]) as conn, conn.cursor() as cur:
        cur.execute(SQL, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=cols)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    kw_tag = _sanitize(code_like) if code_like else "ALL"
    out_xlsx = out_dir / f"barbour_discount_gt{int(min_discount)}_avails_gt{int(min_sizes)}_{kw_tag}_{ts}.xlsx"

    # 写 Excel（需要 openpyxl）
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="discounts")
        # 自动列宽（简易）
        ws = writer.sheets["discounts"]
        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = max((len(str(x)) for x in [col_name] + df[col_name].astype(str).tolist()), default=10)
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = min(max_len + 2, 80)

    print(f"✅ 导出完成：{out_xlsx} （{len(df)} 行）")
    return out_xlsx

# 可选命令行入口
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python export_barbour_discounts_excel.py <min_discount> <min_sizes> [code_like]")
        raise SystemExit(1)
    md = float(sys.argv[1])
    ms = int(sys.argv[2])
    kw = sys.argv[3] if len(sys.argv) >= 4 else None
    export_barbour_discounts_excel(md, ms, kw)
