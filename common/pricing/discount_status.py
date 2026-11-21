# -*- coding: utf-8 -*-
"""
查询商品在供应商端当前是否打折（跨品牌）。

判断：库存表 discount_price_gbp 有值且 < original_price_gbp 即为打折。
Barbour 例外：barbour_inventory 的 original/discount 都写成同一个成本价，看不出折扣，
改从 barbour_offers 取：有货的在售报价优先，没有则取全部在售报价；
原价取各家最高原价，折后价取各家最低现价 —— 任一家卖得比最高原价便宜即算打折。
"""
from __future__ import annotations

import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG, BRAND_TABLE

STATUS_COLUMNS = ["code_key", "original_price_gbp", "discount_price_gbp", "channel_product_ids",
                  "discount_rate", "is_discounted"]


def fetch_discount_status(codes_by_brand: dict[str, list[str]]) -> pd.DataFrame:
    """
    codes_by_brand: {品牌小写: [商品编码, ...]}（编码大小写/空格不敏感）
    返回一行一个编码：code_key（大写）、原价、最低折后价、鲸芽渠道产品ID、折扣率、is_discounted。
    库存表里找不到的编码不返回；品牌不在 BRAND_TABLE 的跳过。
    """
    frames = []
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        for brand, codes in codes_by_brand.items():
            table = BRAND_TABLE.get(str(brand).strip().lower())
            keys = sorted({str(c).strip().upper() for c in codes if str(c).strip()})
            if not table or not keys:
                continue
            sql = f"""
            SELECT UPPER(TRIM(product_code))                       AS code_key,
                   MAX(original_price_gbp)                         AS original_price_gbp,
                   MIN(discount_price_gbp) FILTER (WHERE discount_price_gbp > 0) AS discount_price_gbp,
                   STRING_AGG(DISTINCT NULLIF(TRIM(channel_product_id), ''), ',') AS channel_product_ids
            FROM {table}
            WHERE UPPER(TRIM(product_code)) = ANY(%s)
            GROUP BY UPPER(TRIM(product_code));
            """
            part = pd.read_sql(sql, conn, params=(keys,))
            if table == BRAND_TABLE.get("barbour"):
                part = _override_barbour_prices(conn, part, keys)
            frames.append(part)
    finally:
        conn.close()

    if not frames:
        return pd.DataFrame(columns=STATUS_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    orig = pd.to_numeric(df["original_price_gbp"], errors="coerce")
    disc = pd.to_numeric(df["discount_price_gbp"], errors="coerce")
    df["discount_rate"] = (disc / orig).where(orig > 0).round(2)
    df["is_discounted"] = (orig > 0) & disc.notna() & (disc < orig)
    return df[STATUS_COLUMNS]


def _override_barbour_prices(conn, part: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    # 注意 barbour_offers 字段名：price_gbp = 原价，original_price_gbp = 折后价
    sql = """
    WITH o AS (
      SELECT UPPER(TRIM(product_code)) AS code_key, price_gbp, original_price_gbp,
             COALESCE(stock_count, 0) > 0 AS in_stock
      FROM barbour_offers
      WHERE is_active AND UPPER(TRIM(product_code)) = ANY(%s) AND price_gbp > 0
    ), pick AS (
      SELECT o.* FROM o
      WHERE in_stock OR NOT EXISTS (SELECT 1 FROM o o2 WHERE o2.code_key = o.code_key AND o2.in_stock)
    )
    SELECT code_key,
           MAX(price_gbp)                                                AS offer_original,
           MIN(original_price_gbp) FILTER (WHERE original_price_gbp > 0) AS offer_discount
    FROM pick
    GROUP BY code_key;
    """
    offers = pd.read_sql(sql, conn, params=(keys,))
    part = part.merge(offers, on="code_key", how="left")
    has_offer = part["offer_original"].notna()
    part.loc[has_offer, "original_price_gbp"] = part.loc[has_offer, "offer_original"]
    part.loc[has_offer, "discount_price_gbp"] = part.loc[has_offer, "offer_discount"]
    return part.drop(columns=["offer_original", "offer_discount"])
