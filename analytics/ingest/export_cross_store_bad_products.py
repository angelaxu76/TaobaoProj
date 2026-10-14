"""
跨店铺差商品报告：同一商品编码在所有店铺都表现差、且供应商端没有打折 → 建议删除并加入发布黑名单。

判定规则见 analytics/pipeline/store_config.py 的 BAD_* 参数：
  单店差 = 截至最新日报日期发布满 N 天 且 最近窗口内 浏览量(或访客) < 阈值 且 成交件数 <= 阈值
           且 该店一口价 > 品牌价格阈值（品牌未配置阈值则不限价格）
  差商品 = 在（全部）上架店铺都差
  待删除 = 差商品 且 库存表里未打折（discount_price_gbp 为空或不低于 original_price_gbp）
           Barbour 例外：库存表价格不含折扣信息，改用 barbour_offers 在售报价判断
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG, BRAND_TABLE

CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"
ALLOWED_METRICS = {"pageviews", "visitors"}
METRIC_LABEL = {"pageviews": "浏览量", "visitors": "访客数"}


@dataclass
class BadProductRule:
    stores: list[str]                     # 参与判定的店铺（真实店铺名）
    store_labels: dict[str, str] = field(default_factory=dict)  # 店铺名 → 报表列标签
    window_days: int = 30
    min_publish_days: int = 10
    metric: str = "pageviews"
    metric_max: int = 10
    max_pay_qty: Optional[int] = 0
    require_all_stores: bool = True
    min_price_by_brand: dict[str, float] = field(default_factory=dict)  # 品牌 → 一口价阈值（CNY）


def _fetch_store_detail(rule: BadProductRule) -> tuple[pd.DataFrame, date]:
    """一行一个 (店铺, 商品编码)：最早发布日期、链接、窗口内指标合计。"""
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(stat_date) FROM {DAILY_TABLE} WHERE store_name = ANY(%s);", (rule.stores,))
            end_date = cur.fetchone()[0]
        if end_date is None:
            raise RuntimeError("❌ 日报表中没有这些店铺的数据，请先运行 run_import_data")
        start_date = end_date - timedelta(days=rule.window_days - 1)

        sql = f"""
        WITH d AS (
          SELECT store_name, item_id,
                 SUM(COALESCE(pageviews, 0)) AS pageviews,
                 SUM(COALESCE(visitors, 0))  AS visitors,
                 SUM(COALESCE(pay_qty, 0))   AS pay_qty
          FROM {DAILY_TABLE}
          WHERE stat_date BETWEEN %(start)s AND %(end)s
            AND store_name = ANY(%(stores)s)
          GROUP BY store_name, item_id
        )
        SELECT c.store_name,
               UPPER(TRIM(c.product_code))          AS code_key,
               MAX(TRIM(c.product_code))            AS product_code,
               MAX(LOWER(TRIM(c.brand)))            AS brand,
               MAX(c.item_name)                     AS item_name,
               MIN(c.publication_date)              AS publication_date,
               MAX(c.list_price)                    AS list_price,
               STRING_AGG(DISTINCT c.current_item_id::text, ',') AS item_ids,
               SUM(COALESCE(d.pageviews, 0))        AS pageviews,
               SUM(COALESCE(d.visitors, 0))         AS visitors,
               SUM(COALESCE(d.pay_qty, 0))          AS pay_qty
        FROM {CATALOG_TABLE} c
        LEFT JOIN d ON d.item_id = c.current_item_id AND d.store_name = c.store_name
        WHERE c.store_name = ANY(%(stores)s)
          AND c.product_code IS NOT NULL AND TRIM(c.product_code) <> ''
        GROUP BY c.store_name, UPPER(TRIM(c.product_code));
        """
        df = pd.read_sql(sql, conn, params={"start": start_date, "end": end_date, "stores": rule.stores})
    finally:
        conn.close()
    df["publication_date"] = pd.to_datetime(df["publication_date"]).dt.date
    return df, end_date


def _mark_store_bad(df: pd.DataFrame, rule: BadProductRule, end_date: date) -> pd.DataFrame:
    # 发布天数按日报截止日计算，保证至少有 N 天数据可看
    cutoff = end_date - timedelta(days=rule.min_publish_days)
    bad = df["publication_date"].notna() & (df["publication_date"] <= cutoff)
    bad &= df[rule.metric] < rule.metric_max
    if rule.max_pay_qty is not None:
        bad &= df["pay_qty"] <= rule.max_pay_qty
    if rule.min_price_by_brand:
        price_min = df["brand"].map(rule.min_price_by_brand)
        bad &= price_min.isna() | (pd.to_numeric(df["list_price"], errors="coerce") > price_min)
    df["store_bad"] = bad
    return df


def _fetch_inventory(codes_by_brand: dict[str, list[str]]) -> pd.DataFrame:
    """按品牌查库存表：价格（判断是否打折）+ 鲸芽渠道产品ID。"""
    frames = []
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        for brand, codes in codes_by_brand.items():
            table = BRAND_TABLE.get(brand)
            if not table or not codes:
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
            part = pd.read_sql(sql, conn, params=(codes,))
            if brand == "barbour":
                part = _override_barbour_prices(conn, part, codes)
            part["brand"] = brand
            frames.append(part)
    finally:
        conn.close()
    cols = ["code_key", "original_price_gbp", "discount_price_gbp", "channel_product_ids", "brand"]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)


def _override_barbour_prices(conn, part: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """
    barbour_inventory 的 original/discount 都写成同一个成本价，看不出折扣，
    改从 barbour_offers 取：有货的在售报价优先，没有则取全部在售报价。
    注意 barbour_offers 字段名：price_gbp = 原价，original_price_gbp = 折后价。
    """
    sql = """
    WITH o AS (
      SELECT UPPER(TRIM(product_code)) AS code_key, site_name, price_gbp, original_price_gbp,
             COALESCE(stock_count, 0) > 0 AS in_stock
      FROM barbour_offers
      WHERE is_active AND UPPER(TRIM(product_code)) = ANY(%s) AND price_gbp > 0
    ), pick AS (
      SELECT o.*, MAX(price_gbp) OVER (PARTITION BY code_key) AS max_rrp FROM o
      WHERE in_stock OR NOT EXISTS (SELECT 1 FROM o o2 WHERE o2.code_key = o.code_key AND o2.in_stock)
    )
    -- 原价取各家最高原价，折后价取各家最低现价：任一家卖得比最高原价便宜即算打折
    SELECT code_key,
           MAX(price_gbp)                                                AS offer_original,
           MIN(original_price_gbp) FILTER (WHERE original_price_gbp > 0) AS offer_discount,
           STRING_AGG(DISTINCT site_name, ',')
             FILTER (WHERE original_price_gbp > 0 AND original_price_gbp < max_rrp) AS discount_sites
    FROM pick
    GROUP BY code_key;
    """
    offers = pd.read_sql(sql, conn, params=(codes,))
    part = part.merge(offers, on="code_key", how="left")
    has_offer = part["offer_original"].notna()
    part.loc[has_offer, "original_price_gbp"] = part.loc[has_offer, "offer_original"]
    part.loc[has_offer, "discount_price_gbp"] = part.loc[has_offer, "offer_discount"]
    return part.drop(columns=["offer_original", "offer_discount"])


def _store_values(g: pd.DataFrame, col: str, rule: BadProductRule) -> dict:
    vals = dict(zip(g["store_name"], g[col]))
    return {f"{col}@{rule.store_labels.get(s, s)}": vals.get(s) for s in rule.stores}


def _build_codes(df: pd.DataFrame, rule: BadProductRule) -> pd.DataFrame:
    """一行一个商品编码，判定是否所有上架店铺都差。"""
    rows = []
    for key, g in df.groupby("code_key"):
        store_cnt = g["store_name"].nunique()
        all_bad = bool(g["store_bad"].all())
        if rule.require_all_stores and store_cnt < len(rule.stores):
            all_bad = False
        row = {
            "code_key": key,
            "product_code": g["product_code"].iloc[0],
            "brand": g["brand"].dropna().iloc[0] if g["brand"].notna().any() else None,
            "item_name": g["item_name"].iloc[0],
            "earliest_publication": g["publication_date"].min(),
            "latest_publication": g["publication_date"].max(),
            "store_cnt": store_cnt,
            "is_bad": all_bad,
            f"total_{rule.metric}": int(g[rule.metric].sum()),
            "total_pay_qty": int(g["pay_qty"].sum()),
        }
        row.update(_store_values(g, rule.metric, rule))
        row.update(_store_values(g, "list_price", rule))
        row.update(_store_values(g, "item_ids", rule))
        rows.append(row)
    return pd.DataFrame(rows)


def _reason(row, rule: BadProductRule, end_date: date) -> str:
    label = METRIC_LABEL.get(rule.metric, rule.metric)
    per_store = " / ".join(
        f"{rule.store_labels.get(s, s)} {int(row[f'{rule.metric}@{rule.store_labels.get(s, s)}'])}"
        for s in rule.stores
        if pd.notna(row.get(f"{rule.metric}@{rule.store_labels.get(s, s)}"))
    )
    sold = "，无成交" if rule.max_pay_qty == 0 else ""
    price_min = rule.min_price_by_brand.get(row["brand"])
    price = f"，一口价>{price_min:g}" if price_min is not None else ""
    return (f"{row['store_cnt']}店均表现差：发布满{rule.min_publish_days}天，"
            f"截至{end_date}近{rule.window_days}天{label} {per_store}（阈值<{rule.metric_max}）"
            f"{sold}{price}，未打折；{date.today()} 自动加入")


def build_bad_product_report(rule: BadProductRule) -> dict:
    if rule.metric not in ALLOWED_METRICS:
        raise ValueError(f"BAD_METRIC 只能是 {ALLOWED_METRICS}，当前：{rule.metric}")

    detail, end_date = _fetch_store_detail(rule)
    detail = _mark_store_bad(detail, rule, end_date)
    codes = _build_codes(detail, rule)
    bad = codes[codes["is_bad"]].copy() if not codes.empty else codes

    codes_by_brand = bad.groupby("brand")["code_key"].apply(list).to_dict() if not bad.empty else {}
    inv = _fetch_inventory(codes_by_brand)
    bad = bad.merge(inv.drop(columns="brand"), on="code_key", how="left")

    orig = pd.to_numeric(bad["original_price_gbp"], errors="coerce")
    disc = pd.to_numeric(bad["discount_price_gbp"], errors="coerce")
    bad["discount_rate"] = (disc / orig).where(orig > 0).round(2)
    bad["is_discounted"] = (orig > 0) & disc.notna() & (disc < orig)
    in_inventory = bad["original_price_gbp"].notna() | bad["channel_product_ids"].notna()

    to_delete = bad[in_inventory & ~bad["is_discounted"]].copy()
    to_delete["reason"] = [_reason(r, rule, end_date) for _, r in to_delete.iterrows()]
    kept_discounted = bad[bad["is_discounted"]].copy()
    not_found = bad[~in_inventory].copy()

    jingya_ids = (
        to_delete[["brand", "product_code", "channel_product_ids"]]
        .assign(channel_product_id=lambda x: x["channel_product_ids"].fillna("").str.split(","))
        .explode("channel_product_id")
        .drop(columns="channel_product_ids")
    )
    jingya_ids = jingya_ids[jingya_ids["channel_product_id"].str.strip() != ""].reset_index(drop=True)

    bad_keys = set(bad["code_key"])
    return {
        "end_date": end_date,
        "to_delete": to_delete.sort_values(["brand", "product_code"]).drop(columns=["code_key", "is_bad"]),
        "jingya_ids": jingya_ids,
        "kept_discounted": kept_discounted.drop(columns=["code_key", "is_bad"]),
        "not_found": not_found.drop(columns=["code_key", "is_bad"]),
        "store_detail": detail[detail["code_key"].isin(bad_keys)].drop(columns="code_key"),
        "codes_total": len(codes),
    }


def write_report(result: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    xlsx = output_dir / f"cross_store_bad_products_{stamp}.xlsx"
    txt = output_dir / f"jingya_channel_product_ids_to_delete_{stamp}.txt"

    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        result["to_delete"].to_excel(writer, index=False, sheet_name="待删除")
        result["jingya_ids"].to_excel(writer, index=False, sheet_name="鲸芽ID")
        result["kept_discounted"].to_excel(writer, index=False, sheet_name="差但有折扣_保留")
        result["not_found"].to_excel(writer, index=False, sheet_name="库存表未找到")
        result["store_detail"].to_excel(writer, index=False, sheet_name="店铺明细")
        for ws in writer.sheets.values():
            ws.freeze_panes = "A2"

    txt.write_text("\n".join(result["jingya_ids"]["channel_product_id"].astype(str)), encoding="utf-8")
    return xlsx, txt
