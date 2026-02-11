# -*- coding: utf-8 -*-
"""
方案 1：从 barbour_products 批量“学习/校准”到 barbour_color_map（只导入高频/高置信度）

特点：
- 数据来源：barbour_products
  统计规则：raw_color=lower(trim(color)) -> code2=substring(product_code, 8, 2)
- 仅导入每个颜色的“最高票 code2”，并满足：
    total_cnt >= --min-total
    ratio(最高票/总票) >= --min-ratio
- 写入方式：UPSERT 到 barbour_color_map
  默认使用 ON CONFLICT (color_code, raw_name)

数据库连接：直接复用项目 config.py 中的 PGSQL_CONFIG（不在脚本中写死）
"""

from __future__ import annotations

import argparse
from typing import Tuple

import psycopg2

# ✅ 复用项目配置（不写死）
from config import PGSQL_CONFIG  # noqa: F401


SQL_SELECT_BEST = """
WITH color_votes AS (
  SELECT
    LOWER(TRIM(color))                AS raw_color,
    SUBSTRING(product_code, 8, 2)     AS code2,
    COUNT(*)                          AS cnt
  FROM barbour_products
  WHERE color IS NOT NULL
    AND product_code IS NOT NULL
    AND LENGTH(product_code) >= 9
  GROUP BY 1, 2
),
ranked AS (
  SELECT
    raw_color,
    code2,
    cnt,
    ROW_NUMBER() OVER (PARTITION BY raw_color ORDER BY cnt DESC, code2) AS rn,
    SUM(cnt) OVER (PARTITION BY raw_color)                              AS total_cnt
  FROM color_votes
)
SELECT
  raw_color,
  code2,
  cnt,
  total_cnt,
  (cnt::numeric / NULLIF(total_cnt,0)) AS ratio
FROM ranked
WHERE rn = 1
  AND total_cnt >= %(min_total)s
  AND (cnt::numeric / NULLIF(total_cnt,0)) >= %(min_ratio)s
ORDER BY total_cnt DESC, ratio DESC, raw_color ASC;
"""

SQL_UPSERT = """
INSERT INTO barbour_color_map (color_code, raw_name, norm_key, source, is_confirmed)
VALUES (%(color_code)s, %(raw_name)s, %(norm_key)s, %(source)s, %(is_confirmed)s)
ON CONFLICT (color_code, raw_name) DO UPDATE
SET
  norm_key = EXCLUDED.norm_key,
  source = EXCLUDED.source,
  is_confirmed = EXCLUDED.is_confirmed;
"""

SQL_CONFLICTS = """
WITH x AS (
  SELECT
    LOWER(TRIM(color)) AS raw_color,
    SUBSTRING(product_code, 8, 2) AS code2,
    COUNT(*) AS cnt
  FROM barbour_products
  WHERE color IS NOT NULL AND product_code IS NOT NULL AND LENGTH(product_code) >= 9
  GROUP BY 1,2
),
s AS (
  SELECT raw_color, COUNT(*) AS code2_kinds, SUM(cnt) AS total_cnt
  FROM x
  GROUP BY 1
)
SELECT raw_color, code2_kinds, total_cnt
FROM s
WHERE code2_kinds >= 2
ORDER BY total_cnt DESC, raw_color ASC
LIMIT %(limit)s;
"""


def fetch_best_mappings(conn, min_total: int, min_ratio: float):
    with conn.cursor() as cur:
        cur.execute(SQL_SELECT_BEST, {"min_total": min_total, "min_ratio": min_ratio})
        return cur.fetchall()


def upsert(conn, rows, source: str, dry_run: bool) -> Tuple[int, int]:
    """
    rows: (raw_color, code2, cnt, total_cnt, ratio)
    """
    if dry_run:
        for raw_color, code2, cnt, total_cnt, ratio in rows:
            print(f"[DRY] {raw_color} -> {code2}  cnt={cnt}/{total_cnt} ratio={float(ratio):.3f}")
        return (len(rows), 0)

    n = 0
    with conn.cursor() as cur:
        for raw_color, code2, cnt, total_cnt, ratio in rows:
            cur.execute(
                SQL_UPSERT,
                {
                    "color_code": code2,
                    "raw_name": raw_color,
                    "norm_key": raw_color,
                    "source": source,
                    "is_confirmed": True,
                },
            )
            n += 1
    conn.commit()
    return (n, 0)


def show_conflicts(conn, limit: int):
    with conn.cursor() as cur:
        cur.execute(SQL_CONFLICTS, {"limit": limit})
        rows = cur.fetchall()

    if not rows:
        print("未发现 raw_color -> 多 code2 的冲突颜色。")
        return

    print("\n=== 冲突颜色（同一 raw_color 对多个 code2）===")
    for raw_color, code2_kinds, total_cnt in rows:
        print(f"- {raw_color}: code2_kinds={code2_kinds}, total_cnt={total_cnt}")


def main():
    ap = argparse.ArgumentParser(
        description="从 barbour_products 学习/校准 barbour_color_map（只导入高频/高置信度）"
    )
    ap.add_argument("--min-total", type=int, default=5, help="颜色最少出现次数阈值（默认 5）")
    ap.add_argument("--min-ratio", type=float, default=0.70, help="最高票占比阈值（默认 0.70）")
    ap.add_argument("--source", type=str, default="learned_from_products", help="写入 source 字段（默认 learned_from_products）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要写入的映射，不写库")
    ap.add_argument("--show-conflicts", action="store_true", help="输出冲突颜色列表")
    ap.add_argument("--conflict-limit", type=int, default=50, help="冲突列表最多显示条数（默认 50）")
    args = ap.parse_args()

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        rows = fetch_best_mappings(conn, min_total=args.min_total, min_ratio=args.min_ratio)
        print(f"符合阈值的高置信度映射条数：{len(rows)} (min_total={args.min_total}, min_ratio={args.min_ratio})")

        if not rows:
            print("没有可写入的映射。你可以降低阈值再试。")
            if args.show_conflicts:
                show_conflicts(conn, args.conflict_limit)
            return

        up_cnt, _ = upsert(conn, rows, source=args.source, dry_run=args.dry_run)
        if args.dry_run:
            print(f"\n[DRY-RUN] 预计写入/更新 {up_cnt} 条到 barbour_color_map。")
        else:
            print(f"\n✅ 写入/更新完成：{up_cnt} 条已 upsert 到 barbour_color_map。")

        if args.show_conflicts:
            show_conflicts(conn, args.conflict_limit)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
