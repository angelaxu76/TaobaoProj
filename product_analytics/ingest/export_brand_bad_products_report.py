from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

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
    # 是否按店铺拆分（一般不需要，默认汇总）
    split_by_store: bool = False


def export_brand_bad_products_report(cfg: ExportConfig) -> str:
    out_path = cfg.output_path or rf"D:\TB\Reports\{cfg.brand}_bad_products_last{cfg.days}d.xlsx"

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        # publication_date 条件（可选）
        pub_filter_sql = ""
        params = {"brand": cfg.brand, "days": int(cfg.days)}

        if cfg.min_publication_date is not None:
            pub_filter_sql = "AND c.publication_date < %(min_pub)s"
            params["min_pub"] = cfg.min_publication_date

        # 是否按店铺拆分
        store_select = ", d.store_name" if cfg.split_by_store else ""
        store_group = ", d.store_name" if cfg.split_by_store else ""
        store_out = ", d30.store_name" if cfg.split_by_store else ""

        sql = f"""
        WITH d30 AS (
          SELECT
            d.item_id
            {store_select},
            SUM(COALESCE(d.pageviews, 0))     AS pageviews,
            SUM(COALESCE(d.visitors, 0))      AS visitors,
            SUM(COALESCE(d.fav_cnt, 0))       AS fav_cnt,
            SUM(COALESCE(d.cart_buyer_cnt, 0)) AS cart_buyer_cnt,
            SUM(COALESCE(d.cart_qty, 0))      AS cart_qty,
            SUM(COALESCE(d.pay_qty, 0))       AS pay_qty,
            SUM(COALESCE(d.pay_amount, 0))    AS pay_amount,
            SUM(COALESCE(d.refund_amount, 0)) AS refund_amount
          FROM {DAILY_TABLE} d
          WHERE d.stat_date >= (CURRENT_DATE - INTERVAL '{int(cfg.days)} days')
          GROUP BY d.item_id {store_group}
        )
        SELECT
          c.current_item_id AS item_id,
          c.product_code,
          c.item_name,
          c.brand,
          c.publication_date
          {store_out},
          COALESCE(d30.pageviews, 0)  AS clicks_pageviews_{cfg.days}d,
          COALESCE(d30.visitors, 0)   AS visitors_{cfg.days}d,
          COALESCE(d30.fav_cnt, 0)    AS fav_{cfg.days}d,
          COALESCE(d30.cart_buyer_cnt, 0) AS cart_buyer_{cfg.days}d,
          COALESCE(d30.cart_qty, 0)   AS cart_qty_{cfg.days}d,
          CASE
            WHEN COALESCE(d30.visitors, 0) > 0
              THEN ROUND((COALESCE(d30.cart_buyer_cnt, 0)::numeric / d30.visitors::numeric), 6)
            ELSE 0
          END AS cart_rate_{cfg.days}d,
          COALESCE(d30.pay_qty, 0)    AS sales_qty_{cfg.days}d,
          COALESCE(d30.pay_amount, 0) AS pay_amount_{cfg.days}d,
          COALESCE(d30.refund_amount, 0) AS refund_amount_{cfg.days}d
        FROM {CATALOG_TABLE} c
        LEFT JOIN d30
          ON d30.item_id = c.current_item_id
        WHERE c.brand = %(brand)s
          AND c.current_item_id IS NOT NULL
          {pub_filter_sql}
        ORDER BY
          -- 先把“最不行的”排上来：销量=0、金额低、点击低
          COALESCE(d30.pay_qty, 0) ASC,
          COALESCE(d30.pay_amount, 0) ASC,
          COALESCE(d30.pageviews, 0) ASC,
          c.publication_date ASC NULLS LAST,
          c.product_code ASC;
        """

        df = pd.read_sql(sql, conn, params=params)

        # 输出 Excel
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=f"{cfg.brand}_last{cfg.days}d")

        print(f"✅ 已导出：{out_path}（行数={len(df)}）")
        return out_path
    finally:
        conn.close()


if __name__ == "__main__":
    # 示例：只看发布时间早于 2025-11-01 的商品（更老才展示）
    from datetime import date as _date

    export_brand_bad_products_report(
        ExportConfig(
            brand="CAMPER",
            days=30,
            min_publication_date=_date(2025, 11, 1),  # 可改 None 表示不筛发布时间
            output_path=rf"D:\TB\Reports\CAMPER_bad_products_last30d.xlsx",
            split_by_store=False,
        )
    )
