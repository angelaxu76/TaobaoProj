"""
跨店铺优质商品报告：同一商品编码在所有店铺的浏览、加购、成交合计综合排名靠前 → 直通车推广候选。

规则见 analytics/pipeline/store_config.py 的 TOP_* 参数：
  合计指标 = 最近窗口内该编码在各店铺所有链接之和
  综合得分 = Σ 权重 × 指标在品牌内的百分位排名（0~100）
  入选     = 达到浏览/加购/成交门槛 且 上架店铺数达标，按得分取每个品牌前 N 个
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from cfg.db_config import PGSQL_CONFIG

CATALOG_TABLE = "catalog_items"
DAILY_TABLE = "product_metrics_daily"
METRICS = ["pageviews", "visitors", "fav_cnt", "cart_buyer_cnt", "pay_buyer_cnt", "pay_qty", "pay_amount"]

COLUMN_LABELS = {
    "brand": "品牌",
    "rank": "品牌内排名",
    "product_code": "商品编码",
    "item_name": "商品标题",
    "earliest_publication": "最早发布日期",
    "store_cnt": "上架店铺数",
    "score": "综合得分",
    "pageviews": "总浏览量",
    "visitors": "总访客数",
    "fav_cnt": "总收藏人数",
    "cart_buyer_cnt": "总加购人数",
    "pay_buyer_cnt": "总支付人数",
    "pay_qty": "总成交件数",
    "pay_amount": "总成交金额",
    "cart_rate": "加购率",
    "pay_cvr": "支付转化率",
}


@dataclass
class TopProductRule:
    stores: list[str]                     # 参与统计的店铺（真实店铺名）
    store_labels: dict[str, str] = field(default_factory=dict)  # 店铺名 → 报表列标签
    window_days: int = 30
    weights: dict[str, float] = field(default_factory=lambda: {"pageviews": 0.2, "cart_buyer_cnt": 0.35, "pay_qty": 0.45})
    min_pageviews: int = 50
    min_cart: int = 3
    min_pay_qty: int = 0
    min_store_cnt: int = 1
    top_n_per_brand: int = 30

    def label(self, store: str) -> str:
        return self.store_labels.get(store, store)


def _fetch_store_detail(rule: TopProductRule) -> tuple[pd.DataFrame, date, date]:
    """一行一个 (店铺, 商品编码)：该店所有链接的宝贝ID + 窗口内指标合计。"""
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(stat_date) FROM {DAILY_TABLE} WHERE store_name = ANY(%s);", (rule.stores,))
            end_date = cur.fetchone()[0]
        if end_date is None:
            raise RuntimeError("❌ 日报表中没有这些店铺的数据，请先运行 run_import_data")
        start_date = end_date - timedelta(days=rule.window_days - 1)

        sums_d = ",\n                 ".join(f"SUM(COALESCE({m}, 0)) AS {m}" for m in METRICS)
        sums_c = ",\n               ".join(f"SUM(COALESCE(d.{m}, 0)) AS {m}" for m in METRICS)
        sql = f"""
        WITH d AS (
          SELECT store_name, item_id,
                 {sums_d}
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
               STRING_AGG(DISTINCT c.current_item_id::text, ',') AS item_ids,
               {sums_c}
        FROM {CATALOG_TABLE} c
        LEFT JOIN d ON d.item_id = c.current_item_id AND d.store_name = c.store_name
        WHERE c.store_name = ANY(%(stores)s)
          AND c.product_code IS NOT NULL AND TRIM(c.product_code) <> ''
          AND c.current_item_id IS NOT NULL
        GROUP BY c.store_name, UPPER(TRIM(c.product_code));
        """
        df = pd.read_sql(sql, conn, params={"start": start_date, "end": end_date, "stores": rule.stores})
    finally:
        conn.close()
    df["publication_date"] = pd.to_datetime(df["publication_date"]).dt.date
    return df, start_date, end_date


def _build_codes(detail: pd.DataFrame, rule: TopProductRule) -> pd.DataFrame:
    """一行一个商品编码：各店指标合计 + 每个店铺的宝贝ID / 浏览 / 加购 / 成交。"""
    agg = {m: (m, "sum") for m in METRICS}
    codes = (
        detail.groupby("code_key")
        .agg(product_code=("product_code", "first"),
             brand=("brand", "first"),
             item_name=("item_name", "first"),
             earliest_publication=("publication_date", "min"),
             store_cnt=("store_name", "nunique"),
             **agg)
        .reset_index()
    )
    v = codes["visitors"].astype(float)
    codes["cart_rate"] = np.where(v > 0, (codes["cart_buyer_cnt"] / v).round(4), 0.0)
    codes["pay_cvr"] = np.where(v > 0, (codes["pay_buyer_cnt"] / v).round(4), 0.0)

    # 每个店铺展开：宝贝ID@店铺（多个链接逗号分隔，未上架留空）+ 该店浏览/加购/成交
    per_store = [("item_ids", "宝贝ID"), ("pageviews", "浏览"), ("cart_buyer_cnt", "加购"), ("pay_qty", "成交")]
    for col, title in per_store:
        wide = detail.pivot_table(index="code_key", columns="store_name", values=col, aggfunc="first")
        for s in rule.stores:
            codes[f"{title}@{rule.label(s)}"] = codes["code_key"].map(wide[s]) if s in wide.columns else None
    return codes


def _score(codes: pd.DataFrame, rule: TopProductRule) -> pd.DataFrame:
    """品牌内百分位排名加权：每个指标排名 0~1，乘权重后合计，再缩放到 0~100。"""
    total_w = sum(rule.weights.values())
    score = pd.Series(0.0, index=codes.index)
    for metric, w in rule.weights.items():
        pct = codes.groupby("brand")[metric].rank(pct=True, method="average")
        score += pct.fillna(0) * w
    codes["score"] = (score / total_w * 100).round(1)
    return codes


def build_top_product_report(rule: TopProductRule) -> dict:
    unknown = set(rule.weights) - set(METRICS)
    if unknown:
        raise ValueError(f"TOP_SCORE_WEIGHTS 中有不支持的指标：{unknown}，可选：{METRICS}")

    detail, start_date, end_date = _fetch_store_detail(rule)
    codes = _build_codes(detail, rule)
    codes = codes[codes["brand"].notna()]
    codes = _score(codes, rule)

    ok = (
        (codes["pageviews"] >= rule.min_pageviews)
        & (codes["cart_buyer_cnt"] >= rule.min_cart)
        & (codes["pay_qty"] >= rule.min_pay_qty)
        & (codes["store_cnt"] >= rule.min_store_cnt)
    )
    top = (
        codes[ok]
        .sort_values(["brand", "score", "pay_amount"], ascending=[True, False, False])
        .groupby("brand", group_keys=False)
        .head(rule.top_n_per_brand)
        .copy()
    )
    top["rank"] = top.groupby("brand").cumcount() + 1

    return {
        "start_date": start_date,
        "end_date": end_date,
        "top": top.drop(columns="code_key").reset_index(drop=True),
        "codes_total": len(codes),
        "qualified_total": int(ok.sum()),
    }


def _ordered(df: pd.DataFrame, rule: TopProductRule) -> pd.DataFrame:
    """固定列顺序并改中文表头：总指标在前，各店宝贝ID 紧随其后方便复制。"""
    store_cols = [f"宝贝ID@{rule.label(s)}" for s in rule.stores]
    detail_cols = [f"{t}@{rule.label(s)}" for t in ("浏览", "加购", "成交") for s in rule.stores]
    head = ["brand", "rank", "product_code", "item_name", "score",
            "pageviews", "cart_buyer_cnt", "pay_qty", "pay_amount"]
    tail = ["visitors", "fav_cnt", "pay_buyer_cnt", "cart_rate", "pay_cvr", "store_cnt", "earliest_publication"]
    return df[head + store_cols + tail + detail_cols].rename(columns=COLUMN_LABELS)


def _id_list(top: pd.DataFrame, store: str, rule: TopProductRule) -> pd.DataFrame:
    """某个店铺的直通车ID清单：一行一个宝贝ID（同编码多个链接拆成多行）。"""
    col = f"宝贝ID@{rule.label(store)}"
    ids = top[["brand", "rank", "product_code", "score", col]].dropna(subset=[col])
    ids = ids.assign(**{col: ids[col].str.split(",")}).explode(col)
    return ids.rename(columns={**COLUMN_LABELS, col: "宝贝ID"}).reset_index(drop=True)


def write_report(result: dict, rule: TopProductRule, output_dir: Path) -> Path:
    """
    Excel sheet：
      全部品牌     — 所有入选商品
      <品牌>       — 每个品牌一个 sheet
      ID_<店铺>    — 每个店铺一列纯宝贝ID，直接复制到直通车
      规则说明     — 本次统计窗口与参数
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    xlsx = output_dir / f"cross_store_top_products_{stamp}.xlsx"
    top = result["top"]

    rules = pd.DataFrame([
        ("统计窗口", f"{result['start_date']} ~ {result['end_date']}（{rule.window_days} 天）"),
        ("店铺", "、".join(f"{rule.label(s)}（{s}）" for s in rule.stores)),
        ("综合得分", "品牌内百分位排名加权：" + "，".join(f"{COLUMN_LABELS.get(k, k)} {w:g}" for k, w in rule.weights.items())),
        ("入选门槛", f"总浏览量 >= {rule.min_pageviews}，总加购人数 >= {rule.min_cart}，"
                     f"总成交件数 >= {rule.min_pay_qty}，上架店铺数 >= {rule.min_store_cnt}"),
        ("每品牌数量", f"前 {rule.top_n_per_brand} 个"),
        ("商品编码总数", result["codes_total"]),
        ("达到门槛", result["qualified_total"]),
        ("导出", len(top)),
    ], columns=["项目", "值"])

    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        _ordered(top, rule).to_excel(writer, index=False, sheet_name="全部品牌")
        for brand, g in top.groupby("brand"):
            _ordered(g, rule).to_excel(writer, index=False, sheet_name=brand[:31])
        for s in rule.stores:
            _id_list(top, s, rule).to_excel(writer, index=False, sheet_name=f"ID_{rule.label(s)}"[:31])
        rules.to_excel(writer, index=False, sheet_name="规则说明")
        for ws in writer.sheets.values():
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:50])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 40)
    return xlsx
