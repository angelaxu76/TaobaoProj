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
WITH p1 AS (
  SELECT product_code, MIN(style_name) AS style_name
  FROM barbour_products
  WHERE product_code IS NOT NULL
  GROUP BY product_code
)
SELECT
  o.product_code,
  MIN(p1.style_name) AS product_style_name,
  STRING_AGG(DISTINCT o.site_name, ', ') AS site_names,
  STRING_AGG(DISTINCT o.offer_url, ', ') AS offer_urls,
  MIN(o.price_gbp)::numeric(10,2)          AS price_gbp,
  MIN(o.original_price_gbp)::numeric(10,2) AS original_price,
  MAX(o.discount_pct)                      AS discount_pct,
  STRING_AGG(DISTINCT o.size, ',' ORDER BY o.size) AS sizes_in_stock,
  COUNT(DISTINCT o.size) FILTER (WHERE o.stock_count > 0) AS available_count
FROM barbour_offers o
LEFT JOIN p1
  ON o.product_code = p1.product_code
WHERE o.product_code IS NOT NULL
  AND o.stock_count > 0
  AND o.discount_pct >= %s
  AND (%s IS NULL OR o.product_code ILIKE %s)
  AND o.product_code NOT IN (
    SELECT DISTINCT product_code
    FROM barbour_inventory
    WHERE is_published = TRUE
)
GROUP BY o.product_code
HAVING COUNT(DISTINCT o.size) > %s
ORDER BY discount_pct DESC, price_gbp ASC, o.product_code;
"""


def _sanitize(s: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", s or "")

def export_barbour_discounts_excel(min_discount: float, min_sizes: int, code_like: str | None = None) -> Path:
    """
    导出到 Excel 并返回文件路径
    """
    out_dir: Path = BARBOUR["OUTPUT_DIR"]/ "publication_candidates_excel"
    ensure_all_dirs(out_dir)

    kw_like = f"%{code_like}%" if code_like else None
    params = (min_discount, None if kw_like is None else kw_like, kw_like, min_sizes)

    with psycopg2.connect(**BARBOUR["PGSQL_CONFIG"]) as conn, conn.cursor() as cur:
        cur.execute(SQL, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=cols)
    df = df.sort_values(["discount_pct", "price_gbp", "product_code"], ascending=[False, True, True])\
       .drop_duplicates(subset=["product_code"], keep="first")


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


from typing import Iterable

def _code3_to_int(s: str) -> int:
    # 仅用于类似 "LQU" 这种 3 位 A-Z 代码
    s = s.strip().upper()
    if len(s) != 3 or not s.isalpha():
        raise ValueError(f"code 必须是 3 位字母，如 LQU；收到: {s}")
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A"))
    return n

def _int_to_code3(n: int) -> str:
    if n < 0 or n >= 26**3:
        raise ValueError("code 超出 3 位 A-Z 范围")
    chars = []
    for _ in range(3):
        chars.append(chr(ord("A") + (n % 26)))
        n //= 26
    return "".join(reversed(chars))

def expand_code_like_tokens(code_like_input: str | None) -> list[str] | None:
    """
    支持：
    - None / "" -> None
    - "LQU" -> ["LQU"]
    - "LQU,LWV,LWX" 或 "LQU LWV LWX" -> ["LQU","LWV","LWX"]
    - "LQU-LWX" -> ["LQU","LQV",...,"LWX"]（按 3 位字母 base26 递增）
    """
    if not code_like_input:
        return None

    s = code_like_input.strip().upper()

    # 范围：LQU-LWX
    if "-" in s and len(s.split("-")) == 2:
        a, b = [x.strip().upper() for x in s.split("-")]
        na, nb = _code3_to_int(a), _code3_to_int(b)
        if na > nb:
            na, nb = nb, na
        return [_int_to_code3(i) for i in range(na, nb + 1)]

    # 多个：逗号 / 空格 分隔
    parts = re.split(r"[,\s]+", s)
    parts = [p for p in parts if p]
    return parts or None


def export_barbour_discounts_excel_multi(
    min_discount: float,
    min_sizes: int,
    code_like_input: str | None,
    *,
    one_sheet: bool = True
) -> Path:
    """
    一次导出多个 code_like（支持范围），默认合并到一个 sheet。
    - code_like_input 示例：
      "LQU" / "LQU,LWV" / "LQU LWV" / "LQU-LWX"
    """
    codes = expand_code_like_tokens(code_like_input)

    # 没有 codes 就等同于 ALL：直接走原函数
    if not codes:
        return export_barbour_discounts_excel(min_discount, min_sizes, None)

    out_dir: Path = BARBOUR["OUTPUT_DIR"] / "publication_candidates_excel"
    ensure_all_dirs(out_dir)

    frames = []
    for c in codes:
        out_path = export_barbour_discounts_excel(min_discount, min_sizes, c)
        # 读回来合并（你也可以改成直接复用 SQL 查询避免二次 IO；这个实现最省事、最稳）
        df = pd.read_excel(out_path, sheet_name="discounts")
        df.insert(0, "code_like", c)
        frames.append(df)

    if not frames:
        # 理论不会到这里
        return export_barbour_discounts_excel(min_discount, min_sizes, None)

    merged = pd.concat(frames, ignore_index=True)
    # 同一个 product_code 多个 code_like 命中时，保留折扣最高/价格最低的一条
    merged = merged.sort_values(
        ["discount_pct", "price_gbp", "product_code"],
        ascending=[False, True, True]
    ).drop_duplicates(subset=["product_code"], keep="first")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = _sanitize(code_like_input)
    out_xlsx = out_dir / f"barbour_discount_multi_gt{int(min_discount)}_avails_gt{int(min_sizes)}_{tag}_{ts}.xlsx"

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        if one_sheet:
            merged.to_excel(writer, index=False, sheet_name="discounts_multi")
        else:
            # 每个 code_like 一个 sheet（注意 sheet 名最多 31 字符）
            for c in codes:
                sub = merged[merged["code_like"] == c]
                sheet = c[:31]
                sub.to_excel(writer, index=False, sheet_name=sheet)

    print(f"✅ 导出完成（多 code_like）：{out_xlsx} （{len(merged)} 行，codes={len(codes)}）")
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
