"""
跨店铺差商品报告：价格高 且 无访问 且 无折扣 → 建议从鲸芽删除并加入发布黑名单。

规则（参数见 analytics/pipeline/store_config.py 的 BAD_*，流量指标为最近 window_days 天、所有店铺合计）：
  价格高：各店一口价都 > 品牌阈值（min_price_by_brand；未配置的品牌不限价格）
  无访问：发布满 min_publish_days 天，指标合计 < metric_max，且 成交/加购/收藏 都不超过阈值
  无折扣：common.pricing.discount_status 判断供应商端未打折（Barbour 看 barbour_offers）
三条同时满足 → 待删除；价格高+无访问但有折扣 → 保留；库存表里找不到 → 单独列出不处理

Excel 里带上鲸芽渠道产品ID 和各店淘宝商品ID，便于集中删除。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG
from common.pricing.discount_status import fetch_discount_status

CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"
ALLOWED_METRICS = {"pageviews", "visitors"}
METRIC_LABEL = {"pageviews": "浏览量", "visitors": "访客数"}


@dataclass
class BadProductRule:
    stores: list[str]                     # 参与判定的店铺（真实店铺名）
    store_labels: dict[str, str] = field(default_factory=dict)  # 店铺名 → 报表列标签
    window_days: int = 30
    min_publish_days: int = 30            # 最早发布满 N 天才判断
    metric: str = "pageviews"
    metric_max: int = 30                  # 所有店合计严格小于才算无访问
    max_pay_qty: Optional[int] = 0        # 成交件数上限；None 不看
    max_cart_qty: Optional[int] = 0       # 加购件数上限；None 不看
    max_fav_cnt: Optional[int] = 0        # 收藏数上限；None 不看
    min_price_by_brand: dict[str, float] = field(default_factory=dict)  # 品牌 → 一口价阈值（CNY）


def _label(rule: BadProductRule, store: str) -> str:
    return rule.store_labels.get(store, store)


def _fetch_store_detail(rule: BadProductRule) -> tuple[pd.DataFrame, date]:
    """一行一个 (店铺, 商品编码)：最早发布日期、一口价、淘宝商品ID、窗口内指标合计。"""
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
                 SUM(COALESCE(pay_qty, 0))   AS pay_qty,
                 SUM(COALESCE(cart_qty, 0))  AS cart_qty,
                 SUM(COALESCE(fav_cnt, 0))   AS fav_cnt
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
               MIN(c.list_price)                    AS list_price,
               STRING_AGG(DISTINCT c.current_item_id::text, ',') AS item_ids,
               SUM(COALESCE(d.pageviews, 0))        AS pageviews,
               SUM(COALESCE(d.visitors, 0))         AS visitors,
               SUM(COALESCE(d.pay_qty, 0))          AS pay_qty,
               SUM(COALESCE(d.cart_qty, 0))         AS cart_qty,
               SUM(COALESCE(d.fav_cnt, 0))          AS fav_cnt
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
    df["list_price"] = pd.to_numeric(df["list_price"], errors="coerce")
    return df, end_date


def _build_codes(df: pd.DataFrame, rule: BadProductRule) -> pd.DataFrame:
    """一行一个商品编码：所有店铺合计指标 + 各店一口价/淘宝商品ID。"""
    rows = []
    for key, g in df.groupby("code_key"):
        price = dict(zip(g["store_name"], g["list_price"]))
        ids = dict(zip(g["store_name"], g["item_ids"]))
        row = {
            "code_key": key,
            "product_code": g["product_code"].iloc[0],
            "brand": g["brand"].dropna().iloc[0] if g["brand"].notna().any() else None,
            "item_name": g["item_name"].iloc[0],
            "earliest_publication": g["publication_date"].min(),
            "store_cnt": g["store_name"].nunique(),
            "min_list_price": g["list_price"].min(),
            f"total_{rule.metric}": int(g[rule.metric].sum()),
            "total_pay_qty": int(g["pay_qty"].sum()),
            "total_cart_qty": int(g["cart_qty"].sum()),
            "total_fav_cnt": int(g["fav_cnt"].sum()),
        }
        for s in rule.stores:
            row[f"一口价@{_label(rule, s)}"] = price.get(s)
        for s in rule.stores:
            row[f"淘宝商品ID@{_label(rule, s)}"] = ids.get(s)
        rows.append(row)
    return pd.DataFrame(rows)


def _mark_bad(codes: pd.DataFrame, rule: BadProductRule, end_date: date) -> pd.DataFrame:
    """价格高 且 无访问（是否打折在查完库存表后再判断）。"""
    pub = pd.to_datetime(codes["earliest_publication"])
    bad = pub.notna() & (pub <= pd.Timestamp(end_date - timedelta(days=rule.min_publish_days)))
    bad &= codes[f"total_{rule.metric}"] < rule.metric_max
    for col, lim in (("total_pay_qty", rule.max_pay_qty),
                     ("total_cart_qty", rule.max_cart_qty),
                     ("total_fav_cnt", rule.max_fav_cnt)):
        if lim is not None:
            bad &= codes[col] <= lim
    if rule.min_price_by_brand:
        price_min = codes["brand"].map(rule.min_price_by_brand)
        bad &= price_min.isna() | (codes["min_list_price"] > price_min)
    codes["is_bad"] = bad
    return codes


def _reason(row, rule: BadProductRule, end_date: date) -> str:
    label = METRIC_LABEL.get(rule.metric, rule.metric)
    zero = "、".join(name for name, lim in (("成交", rule.max_pay_qty), ("加购", rule.max_cart_qty),
                                            ("收藏", rule.max_fav_cnt)) if lim == 0)
    price_min = rule.min_price_by_brand.get(row["brand"])
    price = f"一口价>{price_min:g}，" if price_min is not None else ""
    return (f"{price}发布满{rule.min_publish_days}天，截至{end_date}近{rule.window_days}天"
            f"{row['store_cnt']}店合计{label} {int(row[f'total_{rule.metric}'])}（<{rule.metric_max}）"
            f"{f'，无{zero}' if zero else ''}，未打折；{date.today()} 自动加入")


def build_bad_product_report(rule: BadProductRule) -> dict:
    if rule.metric not in ALLOWED_METRICS:
        raise ValueError(f"BAD_METRIC 只能是 {ALLOWED_METRICS}，当前：{rule.metric}")

    detail, end_date = _fetch_store_detail(rule)
    codes = _build_codes(detail, rule)
    if codes.empty:
        raise RuntimeError("❌ catalog_items 中没有这些店铺的商品")
    codes = _mark_bad(codes, rule, end_date)
    bad = codes[codes["is_bad"]].copy()

    codes_by_brand = bad.dropna(subset=["brand"]).groupby("brand")["code_key"].apply(list).to_dict()
    bad = bad.merge(fetch_discount_status(codes_by_brand), on="code_key", how="left")
    bad["is_discounted"] = bad["is_discounted"].fillna(False).astype(bool)
    in_inventory = bad["original_price_gbp"].notna() | bad["channel_product_ids"].notna()

    to_delete = bad[in_inventory & ~bad["is_discounted"]].copy()
    to_delete["reason"] = [_reason(r, rule, end_date) for _, r in to_delete.iterrows()]
    to_delete = to_delete.sort_values(["brand", "product_code"])

    jingya_ids = (
        to_delete[["brand", "product_code", "channel_product_ids"]]
        .assign(channel_product_id=lambda x: x["channel_product_ids"].fillna("").str.split(","))
        .explode("channel_product_id")
        .drop(columns="channel_product_ids")
    )
    jingya_ids = jingya_ids[jingya_ids["channel_product_id"].str.strip() != ""].reset_index(drop=True)

    drop = ["code_key", "is_bad"]
    return {
        "end_date": end_date,
        "to_delete": to_delete.drop(columns=drop),
        "jingya_ids": jingya_ids,
        "kept_discounted": bad[bad["is_discounted"]].drop(columns=drop),
        "not_found": bad[~in_inventory].drop(columns=drop),
        "codes_total": len(codes),
    }


# 待删除 sheet：列顺序 + 中文表头
DELETE_COLUMNS = {
    "brand": "品牌",
    "product_code": "商品编码",
    "item_name": "商品名称",
    "channel_product_ids": "鲸芽渠道产品ID",
}
METRIC_COLUMNS = {
    "earliest_publication": "最早发布日期",
    "store_cnt": "上架店铺数",
    "min_list_price": "最低一口价",
    "total_pay_qty": "成交件数",
    "total_cart_qty": "加购件数",
    "total_fav_cnt": "收藏数",
    "original_price_gbp": "原价GBP",
    "discount_price_gbp": "折后价GBP",
    "discount_rate": "折扣",
    "reason": "原因",
}


def _delete_sheet(df: pd.DataFrame) -> pd.DataFrame:
    store_cols = [c for c in df.columns if c.startswith("淘宝商品ID@")]
    price_cols = [c for c in df.columns if c.startswith("一口价@")]
    metric_cols = [c for c in df.columns if c.startswith("total_") and c not in METRIC_COLUMNS]
    cols = [*DELETE_COLUMNS, *store_cols, *METRIC_COLUMNS, *metric_cols, *price_cols]
    out = df[[c for c in cols if c in df.columns]]
    return out.rename(columns={**DELETE_COLUMNS, **METRIC_COLUMNS,
                               **{c: f"{METRIC_LABEL.get(c[6:], c[6:])}合计" for c in metric_cols}})


def write_report(result: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    xlsx = output_dir / f"cross_store_bad_products_{stamp}.xlsx"
    txt = output_dir / f"jingya_channel_product_ids_to_delete_{stamp}.txt"

    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        _delete_sheet(result["to_delete"]).to_excel(writer, index=False, sheet_name="待删除")
        result["jingya_ids"].rename(columns={"brand": "品牌", "product_code": "商品编码",
                                             "channel_product_id": "鲸芽渠道产品ID"}) \
            .to_excel(writer, index=False, sheet_name="鲸芽渠道产品ID")
        _delete_sheet(result["kept_discounted"]).to_excel(writer, index=False, sheet_name="差但有折扣_保留")
        _delete_sheet(result["not_found"]).to_excel(writer, index=False, sheet_name="库存表未找到")
        for ws in writer.sheets.values():
            ws.freeze_panes = "C2"

    txt.write_text("\n".join(result["jingya_ids"]["channel_product_id"].astype(str)), encoding="utf-8")
    return xlsx, txt
