from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any

import numpy as np
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

    # v3：是否添加 promo_score_100
    add_promo_score: bool = True

    # v3：评分权重（总和=1）
    w_click: float = 0.25
    w_fav: float = 0.20
    w_cart: float = 0.25
    w_order: float = 0.30

    # v3：订单门控的点击阈值（20 是你说的“普通商品大概20点击左右”的基准）
    click_gate_c0: int = 20

    # v3：分位数封顶（防极端爆款拉爆 cap）
    cap_quantile: float = 0.95

    # v3：是否强制最低流量门槛（可选，防“超冷门偶然单”）
    # 例如：min_visitors_for_score=10 表示 visitors<10 的都打 0 分
    min_visitors_for_score: int = 0


def _safe_p95(series: pd.Series, q: float) -> float:
    """计算分位数封顶值，避免 0 导致除零。"""
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    cap = float(np.quantile(s.values, q)) if len(s) else 0.0
    # cap 至少为 1，避免 ln(1+cap)=ln(1)=0
    return max(cap, 1.0)


def _log_norm(x: np.ndarray, cap: float) -> np.ndarray:
    """
    对数归一化到 0~1：
      S = min(1, ln(1+x)/ln(1+cap))
    cap>=1 才安全
    """
    denom = np.log1p(cap)
    if denom <= 0:
        return np.zeros_like(x, dtype=float)
    s = np.log1p(np.maximum(x, 0)) / denom
    return np.clip(s, 0.0, 1.0)


def _compute_promo_score_100(
    df: pd.DataFrame,
    days: int,
    cfg: ExportConfig,
) -> pd.Series:
    """
    只基于四个漏斗数字计算 promo_score_100：
      click  = visitors_{days}d
      fav    = fav_{days}d
      cart   = cart_buyer_{days}d
      order  = sales_qty_{days}d

    分数模型（0~100）：
      score = 100 * (
          w_click*S_click
        + w_fav*S_fav
        + w_cart*S_cart
        + w_order*S_order * g
      )

    g 为订单门控（防偶然单）：
      g = min(1, ln(1+click)/ln(1+C0))
    """
    click_col = f"visitors_{days}d"
    fav_col = f"fav_{days}d"
    cart_col = f"cart_buyer_{days}d"
    order_col = f"sales_qty_{days}d"

    for col in [click_col, fav_col, cart_col, order_col]:
        if col not in df.columns:
            raise KeyError(f"缺少字段 {col}，无法计算 promo_score_100。请检查 SQL 输出列名。")

    click = pd.to_numeric(df[click_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    fav = pd.to_numeric(df[fav_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    cart = pd.to_numeric(df[cart_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    order = pd.to_numeric(df[order_col], errors="coerce").fillna(0).to_numpy(dtype=float)

    # 分位数封顶（P95）
    cap_click = _safe_p95(df[click_col], cfg.cap_quantile)
    cap_fav = _safe_p95(df[fav_col], cfg.cap_quantile)
    cap_cart = _safe_p95(df[cart_col], cfg.cap_quantile)
    cap_order = _safe_p95(df[order_col], cfg.cap_quantile)

    s_click = _log_norm(click, cap_click)
    s_fav = _log_norm(fav, cap_fav)
    s_cart = _log_norm(cart, cap_cart)
    s_order = _log_norm(order, cap_order)

    # 订单门控：点击不足时，订单分按比例打折（防“冷商品偶然一单”）
    c0 = max(int(cfg.click_gate_c0), 1)
    g = _log_norm(click, c0)  # cap=c0 等价于 ln(1+click)/ln(1+c0)，再 clip 到 0~1

    score = 100.0 * (
        cfg.w_click * s_click
        + cfg.w_fav * s_fav
        + cfg.w_cart * s_cart
        + cfg.w_order * (s_order * g)
    )

    # 可选：最低流量门槛（超冷直接 0）
    if cfg.min_visitors_for_score and cfg.min_visitors_for_score > 0:
        score = np.where(click < cfg.min_visitors_for_score, 0.0, score)

    return pd.Series(np.round(score, 2), index=df.index, name="promo_score_100")


def export_brand_bad_products_report(cfg: ExportConfig) -> str:
    """
    导出该品牌商品最近 N 天表现（按日表求和）。
    v3：输出时仅新增一个 promo_score_100（0~100），用于关键词推广选品筛选。
    """
    if not cfg.output_path:
        cfg.output_path = rf"D:\TB\product_analytics\export\{cfg.brand}_bad_products_last{cfg.days}d.xlsx"

    # 时间窗口（严格 N 天）
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
    params: Dict[str, Any] = {
        "brand": cfg.brand,
        "min_pub": cfg.min_publication_date,
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
      COALESCE(d30.pay_qty, 0) ASC,
      COALESCE(d30.pay_amount, 0) ASC,
      COALESCE(d30.pageviews, 0) ASC,
      c.publication_date ASC NULLS LAST,
      c.product_code ASC;
    """

    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        df = pd.read_sql(sql, conn, params=params)

        # v3：只加一个 promo_score_100
        if cfg.add_promo_score and len(df) > 0:
            df["promo_score_100"] = _compute_promo_score_100(df, cfg.days, cfg)

        sheet_name = f"{cfg.brand}_last{cfg.days}d"
        with pd.ExcelWriter(cfg.output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)

        print(f"✅ 已导出：{cfg.output_path}（行数={len(df)}）")
        return cfg.output_path
    finally:
        conn.close()


if __name__ == "__main__":
    export_brand_bad_products_report(
        ExportConfig(
            brand="camper",
            days=30,
            split_by_store=False,
            include_today=False,
            min_publication_date=None,
            output_path=None,
            add_promo_score=True,
            # 你也可以按需调整：
            # click_gate_c0=20,
            # cap_quantile=0.95,
            # min_visitors_for_score=10,
        )
    )
