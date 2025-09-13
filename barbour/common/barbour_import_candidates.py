# -*- coding: utf-8 -*-
"""
barbour_import_candidates.py
集中式候选池/回填/导入工具（供 pipeline 调用）

子命令：
  1)  python barbour_import_candidates.py import-from-txt [supplier]
      - 扫描 BARBOUR['TXT_DIRS'][supplier] 下的 TXT
      - 有编码 -> 写 barbour_products（source_rank=1）
      - 无编码 -> 写 barbour_product_candidates

  2)  python barbour_import_candidates.py export-excel --out D:\TB\Products\barbour\output\barbour_candidates.xlsx
      - 导出 barbour_product_candidates 为 Excel，首列留空 product_code 供人工填写

  3)  python barbour_import_candidates.py import-codes --in D:\TB\Products\barbour\output\barbour_candidates.xlsx
      - 读取 Excel，把编码以 source_rank=2 回填至 barbour_products，并删除候选

  4)  可供抓取脚本调用：
      from barbour_import_candidates import find_code_by_site_url
      code = find_code_by_site_url(conn, "very", url)

依赖：psycopg2、pandas、openpyxl
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg2
import pandas as pd

# === 复用你项目里的配置 & 工具 ===
from config import PGSQL_CONFIG, BARBOUR
# 直接复用你现有的解析/清洗方法，避免两份逻辑漂移
from barbour.common.barbour_import_to_barbour_products import (
    _extract_field, _extract_multiline_field,
    _parse_sizes_from_size_detail_line,
    extract_match_keywords, enrich_record_optional
)

# ========== 常量 ==========
RE_CODE = re.compile(r'^[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}$')  # 例如 MWX0339NY91

# ========== DB 工具 ==========
def get_conn():
    return psycopg2.connect(**PGSQL_CONFIG)

# ========== 解析 TXT ==========
def parse_txt(filepath: Path) -> Dict:
    text = filepath.read_text(encoding="utf-8", errors="ignore")

    code = _extract_field(text, r'(?i)Product\s+(?:Color\s+)?Code')
    code = (code or "").strip()
    if code.lower() in {"", "no data", "null"}:
        code = None

    style_name = _extract_field(text, r'(?i)Product\s+Name') or ""
    color = _extract_field(text, r'(?i)Product\s+Colou?r') or ""
    if color:
        # 去掉形如 "---- Navy" 的破折号前缀
        import re as _re
        color = _re.sub(r'^\-+\s*', '', color).strip()

    desc = _extract_multiline_field(text, r'(?i)Product\s+Description')
    gender = _extract_field(text, r'(?i)Product\s+Gender')
    category = _extract_field(text, r'(?i)Style\s+Category')
    sizes = _parse_sizes_from_size_detail_line(text)  # 仅提尺码
    source_site = (_extract_field(text, r'(?i)Site\s+Name') or "").strip()
    source_url  = (_extract_field(text, r'(?i)Source\s+URL') or "").strip()

    return {
        "product_code": code,
        "style_name": style_name,
        "color": color,
        "product_description": desc,
        "gender": gender,
        "category": category,
        "sizes": sizes,
        "source_site": source_site,
        "source_url": source_url,
    }

# ========== 导入：TXT -> products / candidates ==========
def import_from_txt(supplier: str = "all") -> None:
    # 收集 TXT 路径
    txt_dirs = BARBOUR.get("TXT_DIRS", {}) or {}
    paths: List[Path] = []
    if supplier == "all":
        for d in txt_dirs.values():
            p = Path(d)
            if p.exists():
                paths += sorted(p.glob("*.txt"))
    else:
        p = Path(txt_dirs.get(supplier, ""))
        if p.exists():
            paths = sorted(p.glob("*.txt"))

    if not paths:
        print(f"⚠ 未找到 TXT（supplier='{supplier}'）。请检查 BARBOUR['TXT_DIRS'] 配置。")
        return

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # products：以 rank=1（有编码站点）写入；冲突时遵循你原来的“rank 保护覆盖”语义
            sql_prod = """
            INSERT INTO barbour_products
              (product_code, style_name, color, size, match_keywords,
               title, product_description, gender, category,
               source_site, source_url, source_rank)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
            ON CONFLICT (product_code, size) DO UPDATE SET
               style_name = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.style_name ELSE barbour_products.style_name END,
               color      = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.color      ELSE barbour_products.color      END,
               title               = COALESCE(barbour_products.title, EXCLUDED.title),
               product_description = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.product_description, barbour_products.product_description) ELSE barbour_products.product_description END,
               gender              = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.gender, barbour_products.gender) ELSE barbour_products.gender END,
               category            = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.category, barbour_products.category) ELSE barbour_products.category END,
               source_site         = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_site ELSE barbour_products.source_site END,
               source_url          = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_url  ELSE barbour_products.source_url  END,
               source_rank         = LEAST(barbour_products.source_rank, EXCLUDED.source_rank);
            """

            # candidates：无编码先入候选池（site+url+size 唯一）
            sql_cand = """
            INSERT INTO barbour_product_candidates
              (site_name, source_url, style_name, color, size,
               gender, category, title, product_description, match_keywords)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (site_name, source_url, size) DO UPDATE SET
              style_name=EXCLUDED.style_name,
              color=EXCLUDED.color,
              gender=COALESCE(EXCLUDED.gender, barbour_product_candidates.gender),
              category=COALESCE(EXCLUDED.category, barbour_product_candidates.category),
              title=COALESCE(EXCLUDED.title, barbour_product_candidates.title),
              product_description=COALESCE(EXCLUDED.product_description, barbour_product_candidates.product_description),
              match_keywords=COALESCE(EXCLUDED.match_keywords, barbour_product_candidates.match_keywords);
            """

            total_ok, total_cand = 0, 0
            for fp in paths:
                info = parse_txt(fp)
                sizes = info.get("sizes") or []
                if not sizes or not info.get("style_name") or not info.get("color"):
                    # 信息不完整，跳过
                    print(f"ⓘ 跳过（信息不完整）: {fp.name}")
                    continue

                # 关键词提取 + 轻量 enrich（不覆盖已有值）
                kws = extract_match_keywords(info["style_name"])
                base = {
                    "style_name": info["style_name"],
                    "color": info["color"],
                    "title": None,
                    "product_description": info.get("product_description"),
                    "gender": info.get("gender"),
                    "category": info.get("category"),
                }
                base = enrich_record_optional(base)

                if info.get("product_code"):
                    # 有编码 → 直接进 products
                    for sz in sizes:
                        cur.execute(sql_prod, (
                            info["product_code"], base["style_name"], base["color"], sz,
                            kws, base.get("title"), base.get("product_description"),
                            base.get("gender"), base.get("category"),
                            info["source_site"], info["source_url"]
                        ))
                        total_ok += 1
                else:
                    # 无编码 → 进候选池
                    for sz in sizes:
                        cur.execute(sql_cand, (
                            info["source_site"], info["source_url"], base["style_name"], base["color"], sz,
                            base.get("gender"), base.get("category"), base.get("title"),
                            base.get("product_description"), kws
                        ))
                        total_cand += 1

        print(f"✔ 导入完成：products 写入 {total_ok} 条；candidates 写入 {total_cand} 条。")
    finally:
        conn.close()

# ========== 导出候选池为 Excel ==========
def export_candidates_excel(out_path: str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn()
    try:
        sql = """
        SELECT site_name, source_url, style_name, color, size,
               gender, category, title, product_description
          FROM barbour_product_candidates
         ORDER BY site_name, style_name, color, size;
        """
        df = pd.read_sql(sql, conn)
        # 在首列插入空 product_code 供人工填写
        df.insert(0, "product_code", "")
        df.to_excel(out, index=False)
        print(f"✔ 导出完成：{out}")
    finally:
        conn.close()

# ========== 从 Excel 回填编码到 products（rank=2），并删除候选 ==========
def import_codes_from_excel(in_path: str) -> None:
    src = Path(in_path)
    if not src.exists():
        print(f"❌ 找不到 Excel：{src}")
        return

    df = pd.read_excel(src).fillna("")
    rows: List[Tuple] = []
    bad_codes: List[str] = []

    for _, r in df.iterrows():
        code = str(r.get("product_code", "")).strip().upper()
        if not code:
            continue
        if not RE_CODE.match(code):
            bad_codes.append(code)
            continue
        rows.append((
            code, r.get("style_name",""), r.get("color",""), r.get("size",""),
            (r.get("gender") or None), (r.get("category") or None),
            (r.get("title") or None), (r.get("product_description") or None),
            r.get("site_name",""), r.get("source_url","")
        ))

    if bad_codes:
        print("⚠ 下列编码格式不合法，已跳过：", bad_codes)

    if not rows:
        print("ⓘ 没有可回填的行。")
        return

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            upsert = """
            INSERT INTO barbour_products
              (product_code, style_name, color, size, match_keywords,
               title, product_description, gender, category,
               source_site, source_url, source_rank)
            VALUES (%s,%s,%s,%s,ARRAY[]::TEXT[],%s,%s,%s,%s,%s,%s,2)
            ON CONFLICT (product_code, size) DO UPDATE SET
               style_name = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.style_name ELSE barbour_products.style_name END,
               color      = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.color      ELSE barbour_products.color      END,
               title               = COALESCE(barbour_products.title, EXCLUDED.title),
               product_description = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.product_description, barbour_products.product_description) ELSE barbour_products.product_description END,
               gender              = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.gender, barbour_products.gender) ELSE barbour_products.gender END,
               category            = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.category, barbour_products.category) ELSE barbour_products.category END,
               source_site         = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_site ELSE barbour_products.source_site END,
               source_url          = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_url  ELSE barbour_products.source_url  END,
               source_rank         = LEAST(barbour_products.source_rank, EXCLUDED.source_rank);
            """
            delete_cand = """
            DELETE FROM barbour_product_candidates
             WHERE site_name=%s AND source_url=%s AND size=%s;
            """
            n = 0
            for (code, name, color, size, gender, cat, title, desc, site, url) in rows:
                if not all([code, name, color, size]):
                    continue
                cur.execute(upsert, (
                    code, name, color, size,
                    title, desc, gender, cat, site, url
                ))
                # 清候选
                cur.execute(delete_cand, (site, url, size))
                n += 1
        print(f"✔ 已回填编码到 barbour_products，并清理候选 {n} 行。")
    finally:
        conn.close()

# ========== 抓取侧可复用的小工具（very/hof 在写 TXT 前先查一把） ==========
def find_code_by_site_url(conn_or_cursor, site_name: str, source_url: str) -> Optional[str]:
    """
    供 very/houseoffraser 抓取脚本调用：
      code = find_code_by_site_url(conn, "very", url)
    命中则直接用这枚编码命名 TXT；命不中再走相似度匹配兜底。
    """
    # 支持传 psycopg2 连接或 cursor
    if hasattr(conn_or_cursor, "cursor"):
        cur = conn_or_cursor.cursor()
        owns = True
    else:
        cur = conn_or_cursor
        owns = False
    try:
        cur.execute("""
            SELECT DISTINCT product_code
              FROM barbour_products
             WHERE lower(source_site)=lower(%s)
               AND source_url=%s
             LIMIT 1
        """, (site_name, source_url))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        if owns:
            try: cur.close()
            except Exception: pass

# ========== CLI ==========
def main():
    ap = argparse.ArgumentParser(description="Barbour 候选池/回填 工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("import-from-txt", help="扫描 TXT，写入 products/candidates")
    p1.add_argument("supplier", nargs="?", default="all", help="supplier 名；默认 all")

    p2 = sub.add_parser("export-excel", help="导出候选池为 Excel（首列留空 product_code）")
    p2.add_argument("--out", required=True, help="输出 Excel 路径")

    p3 = sub.add_parser("import-codes", help="读取 Excel 回填编码到 products，并删除候选")
    p3.add_argument("--in", dest="in_path", required=True, help="输入 Excel 路径")

    args = ap.parse_args()

    if args.cmd == "import-from-txt":
        import_from_txt(args.supplier)
    elif args.cmd == "export-excel":
        export_candidates_excel(args.out)
    elif args.cmd == "import-codes":
        import_codes_from_excel(args.in_path)

if __name__ == "__main__":
    main()
