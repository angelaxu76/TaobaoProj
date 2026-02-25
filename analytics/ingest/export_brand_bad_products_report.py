from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any

import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG


CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"


@dataclass
class ExportConfig:
    brand: str
    days: int = 30
    # 只显示 publication_date < 该日期 的商品（更老才显示）
    min_publication_date: Optional[date] = None
    output_path: Optional[str] = None
    # 是否按店铺拆分（默认汇总）
    split_by_store: bool = False
    # 是否包含“今天”（True: [today-days+1, today]；False: [today-days, today)）
    include_today: bool = False


def export_brand_bad_products_report(cfg: ExportConfig) -> str:
    """
    导出该品牌商品最近 N 天表现（按日表求和）。
    """
    if not cfg.output_path:
        cfg.output_path = rf"D:\TB\product_analytics\export\{cfg.brand}_bad_products_last{cfg.days}d.xlsx"

    # 时间窗口（严格 N 天）
    # include_today=False: 统计区间 [CURRENT_DATE - N days, CURRENT_DATE)
    # include_today=True : 统计区间 [CURRENT_DATE - (N-1) days, CURRENT_DATE] 约等于“含今天最近N天”
    if cfg.include_today:
        start_expr = f"(CURRENT_DATE - INTERVAL '{int(cfg.days) - 1} days')"
        end_expr = "CURRENT_DATE"
        end_op = "<="
    else:
        start_expr = f"(CURRENT_DATE - INTERVAL '{int(cfg.days)} days')"
        end_expr = "CURRENT_DATE"
        end_op = "<"

    # 是否按店铺拆分
    store_select = ", d.store_name AS store_name" if cfg.split_by_store else ""
    store_group = ", d.store_name" if cfg.split_by_store else ""
    store_out = ", d30.store_name" if cfg.split_by_store else ""

    # min_publication_date 过滤（可选，且保留 NULL）
    pub_filter_sql = ""
    params: Dict[str, Any] = {
        "brand": cfg.brand,
        "min_pub": cfg.min_publication_date,  # 即使 None 也传进去，SQL 里判断
    }

    pub_filter_sql = """
      AND (
            %(min_pub)s IS NULL
            OR c.publication_date < %(min_pub)s
            OR c.publication_date IS NULL
          )
    """

    sql = f"""
    WITH d30 AS (
      SELECT
        d.item_id AS item_id
        {store_select},
        SUM(COALESCE(d.pageviews, 0))        AS pageviews,
        SUM(COALESCE(d.visitors, 0))         AS visitors,
        SUM(COALESCE(d.fav_cnt, 0))          AS fav_cnt,
        SUM(COALESCE(d.cart_buyer_cnt, 0))   AS cart_buyer_cnt,
        SUM(COALESCE(d.cart_qty, 0))         AS cart_qty,
        SUM(COALESCE(d.pay_qty, 0))          AS pay_qty,
        SUM(COALESCE(d.pay_amount, 0))       AS pay_amount,
        SUM(COALESCE(d.refund_amount, 0))    AS refund_amount
      FROM {DAILY_TABLE} d
      WHERE d.stat_date >= {start_expr}
        AND d.stat_date {end_op} {end_expr}
      GROUP BY d.item_id {store_group}
    )
    SELECT
      c.current_item_id AS item_id,
      c.product_code,
      c.item_name,
      c.brand,
      c.publication_date
      {store_out},

      COALESCE(d30.pageviews, 0)     AS clicks_pageviews_{int(cfg.days)}d,
      COALESCE(d30.visitors, 0)      AS visitors_{int(cfg.days)}d,
      COALESCE(d30.fav_cnt, 0)       AS fav_{int(cfg.days)}d,
      COALESCE(d30.cart_buyer_cnt, 0) AS cart_buyer_{int(cfg.days)}d,
      COALESCE(d30.cart_qty, 0)      AS cart_qty_{int(cfg.days)}d,

      CASE
        WHEN COALESCE(d30.visitors, 0) > 0
          THEN ROUND((COALESCE(d30.cart_buyer_cnt, 0)::numeric / d30.visitors::numeric), 6)
        ELSE 0
      END AS cart_rate_{int(cfg.days)}d,

      COALESCE(d30.pay_qty, 0)       AS sales_qty_{int(cfg.days)}d,
      COALESCE(d30.pay_amount, 0)    AS pay_amount_{int(cfg.days)}d,
      COALESCE(d30.refund_amount, 0) AS refund_amount_{int(cfg.days)}d

    FROM {CATALOG_TABLE} c
    LEFT JOIN d30
      ON d30.item_id = c.current_item_id

    WHERE LOWER(TRIM(c.brand)) = LOWER(TRIM(%(brand)s))
      {pub_filter_sql}

    ORDER BY
      -- 排查“不行商品”：销量=0、成交金额低、点击低
      COALESCE(d30.pay_qty, 0) ASC,
      COALESCE(d30.pay_amount, 0) ASC,
      COALESCE(d30.pageviews, 0) ASC,
      c.publication_date ASC NULLS LAST,
      c.product_code ASC;
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        df = pd.read_sql(sql, conn, params=params)

        with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=f"{cfg.brand}_last{cfg.days}d")

        print(f"✅ 已导出：{cfg.output_path}（行数={len(df)}）")
        return cfg.output_path
    finally:
        conn.close()
