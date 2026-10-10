from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

import numpy as np
import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG

CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"

# 对比 sheet 中按店铺展开的指标
PIVOT_METRICS: List[str] = ["link_cnt", "visitors", "fav_cnt", "cart_buyer_cnt", "pay_qty", "pay_amount", "cart_rate", "pay_cvr"]


@dataclass
class CrossStoreConfig:
    brand: Optional[str] = None         # None = 全部品牌
    days: int = 30                      # 统计窗口：[today-days, today)
    output_path: Optional[str] = None
    # 对比 sheet 只保留至少在 N 个店铺上架的商品（1 = 全部保留）
    min_store_cnt: int = 2


def _fetch(cfg: CrossStoreConfig) -> pd.DataFrame:
    """
    按 (店铺, 商品编码) 聚合最近 N 天表现。
    以 catalog_items 为主表 LEFT JOIN 日报：在某店上架但没有流量的商品也会出现（指标为 0）。
    同一店铺同一编码可能有多个链接，link_cnt 记录链接数，指标为多个链接之和。
    """
    params = {"brand": cfg.brand}
    brand_filter = "AND LOWER(TRIM(c.brand)) = LOWER(TRIM(%(brand)s))" if cfg.brand else ""

    sql = f"""
    WITH d AS (
      SELECT
        d.store_name,
        d.item_id,
        SUM(COALESCE(d.visitors, 0))       AS visitors,
        SUM(COALESCE(d.pageviews, 0))      AS pageviews,
        SUM(COALESCE(d.fav_cnt, 0))        AS fav_cnt,
        SUM(COALESCE(d.cart_buyer_cnt, 0)) AS cart_buyer_cnt,
        SUM(COALESCE(d.pay_qty, 0))        AS pay_qty,
        SUM(COALESCE(d.pay_buyer_cnt, 0))  AS pay_buyer_cnt,
        SUM(COALESCE(d.pay_amount, 0))     AS pay_amount
      FROM {DAILY_TABLE} d
      WHERE d.stat_date >= (CURRENT_DATE - INTERVAL '{int(cfg.days)} days')
        AND d.stat_date < CURRENT_DATE
      GROUP BY d.store_name, d.item_id
    )
    SELECT
      c.store_name,
      c.brand,
      c.product_code,
      MAX(c.item_name)                         AS item_name,
      MIN(c.publication_date)                  AS publication_date,
      COUNT(DISTINCT c.current_item_id)        AS link_cnt,
      SUM(COALESCE(d.visitors, 0))             AS visitors,
      SUM(COALESCE(d.pageviews, 0))            AS pageviews,
      SUM(COALESCE(d.fav_cnt, 0))              AS fav_cnt,
      SUM(COALESCE(d.cart_buyer_cnt, 0))       AS cart_buyer_cnt,
      SUM(COALESCE(d.pay_qty, 0))              AS pay_qty,
      SUM(COALESCE(d.pay_buyer_cnt, 0))        AS pay_buyer_cnt,
      SUM(COALESCE(d.pay_amount, 0))           AS pay_amount
    FROM {CATALOG_TABLE} c
    LEFT JOIN d
      ON d.item_id = c.current_item_id
     AND d.store_name = c.store_name
    WHERE c.product_code IS NOT NULL
      AND c.store_name IS NOT NULL
      {brand_filter}
    GROUP BY c.store_name, c.brand, c.product_code
    ORDER BY c.brand, c.product_code, c.store_name;
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    visitors = df["visitors"].astype(float)
    df["cart_rate"] = np.where(visitors > 0, (df["cart_buyer_cnt"] / visitors).round(4), 0.0)
    df["pay_cvr"] = np.where(visitors > 0, (df["pay_buyer_cnt"] / visitors).round(4), 0.0)
    return df


def _build_pivot(df: pd.DataFrame, cfg: CrossStoreConfig) -> pd.DataFrame:
    """
    一行一个商品编码，每个指标按店铺展开成列：visitors@店铺A、visitors@店铺B ...
    并标出访客最多 / 成交最多的店铺。
    """
    if df.empty:
        return pd.DataFrame()

    keys = ["brand", "product_code"]
    base = (
        df.groupby(keys)
        .agg(item_name=("item_name", "first"),
             publication_date=("publication_date", "min"),
             store_cnt=("store_name", "nunique"),
             total_visitors=("visitors", "sum"),
             total_pay_qty=("pay_qty", "sum"),
             total_pay_amount=("pay_amount", "sum"))
        .reset_index()
    )

    stores = sorted(df["store_name"].unique())
    wide = df.pivot_table(index=keys, columns="store_name", values=PIVOT_METRICS, aggfunc="sum")
    # 不在某店上架的商品：对应店铺列留空（区别于"上架了但为 0"）
    wide = wide.reindex(columns=pd.MultiIndex.from_product([PIVOT_METRICS, stores]))
    wide.columns = [f"{metric}@{store}" for metric, store in wide.columns]
    wide = wide.reset_index()

    out = base.merge(wide, on=keys, how="left")

    def _best_store(metric: str) -> pd.Series:
        cols = [f"{metric}@{s}" for s in stores]
        vals = out[cols].fillna(-1)
        best = vals.idxmax(axis=1).str.split("@", n=1).str[1]
        # 所有店都为 0 时没有"最好"的店
        return best.where(vals.max(axis=1) > 0, "")

    out["best_store_by_visitors"] = _best_store("visitors")
    out["best_store_by_pay_amount"] = _best_store("pay_amount")

    out = out[out["store_cnt"] >= cfg.min_store_cnt]
    return out.sort_values(["total_pay_amount", "total_visitors"], ascending=False).reset_index(drop=True)


def _build_store_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    s = (
        df.groupby("store_name")
        .agg(product_cnt=("product_code", "nunique"),
             link_cnt=("link_cnt", "sum"),
             visitors=("visitors", "sum"),
             fav_cnt=("fav_cnt", "sum"),
             cart_buyer_cnt=("cart_buyer_cnt", "sum"),
             pay_buyer_cnt=("pay_buyer_cnt", "sum"),
             pay_qty=("pay_qty", "sum"),
             pay_amount=("pay_amount", "sum"))
        .reset_index()
    )
    v = s["visitors"].astype(float)
    s["cart_rate"] = np.where(v > 0, (s["cart_buyer_cnt"] / v).round(4), 0.0)
    s["pay_cvr"] = np.where(v > 0, (s["pay_buyer_cnt"] / v).round(4), 0.0)
    s["visitors_per_product"] = (v / s["product_cnt"]).round(1)
    return s


def export_cross_store_comparison(cfg: CrossStoreConfig) -> str:
    """
    导出同一商品在多个店铺的表现对比，三个 sheet：
      对比     — 一行一个商品编码，指标按店铺展开（只保留 store_cnt >= min_store_cnt 的商品）
      明细     — 一行一个 (店铺, 商品编码)
      店铺汇总 — 各店铺该品牌整体表现
    """
    label = cfg.brand or "all"
    if not cfg.output_path:
        cfg.output_path = rf"D:\TB\product_analytics\cross_store\export\{label}_cross_store_last{cfg.days}d.xlsx"

    df = _fetch(cfg)
    pivot = _build_pivot(df, cfg)
    summary = _build_store_summary(df)

    with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
        pivot.to_excel(writer, index=False, sheet_name="对比")
        df.to_excel(writer, index=False, sheet_name="明细")
        summary.to_excel(writer, index=False, sheet_name="店铺汇总")

    print(f"✅ 已导出：{cfg.output_path}（对比 {len(pivot)} 个商品，明细 {len(df)} 行，店铺 {df['store_name'].nunique()} 个）")
    return cfg.output_path


if __name__ == "__main__":
    export_cross_store_comparison(CrossStoreConfig(brand="camper", days=30))
