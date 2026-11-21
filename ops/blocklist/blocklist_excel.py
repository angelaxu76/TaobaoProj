"""发布黑名单 ⇄ Excel 转换（导出 / 导入 / 旧 Excel 迁移共用）。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.publication.publish_blocklist import read_blocklist

# 数据库字段 → Excel 中文表头（导出顺序）
EXPORT_COLUMNS = {
    "product_code": "商品编码",
    "brand": "品牌",
    "is_active": "启用",
    "release_on_discount": "打折后可发布",
    "cur_is_discounted": "当前是否打折",
    "cur_original_price_gbp": "当前原价GBP",
    "cur_discount_price_gbp": "当前折后价GBP",
    "discount_checked_at": "折扣检查时间",
    "released_at": "打折放行时间",
    "original_price_gbp": "加入时原价GBP",
    "discount_price_gbp": "加入时折后价GBP",
    "discount_rate": "加入时折扣",
    "block_count": "加入次数",
    "source": "来源",
    "reason": "原因",
    "note": "备注",
    "first_blocked_at": "首次加入时间",
    "last_blocked_at": "最近加入时间",
}
BOOL_COLUMNS = ["is_active", "release_on_discount", "cur_is_discounted"]
YES = {"是", "Y", "YES", "TRUE", "1"}
NO = {"否", "N", "NO", "FALSE", "0"}

# 导入时读取的列（其余列只读）
IMPORT_COLUMNS = {"商品编码": "product_code", "品牌": "brand", "启用": "is_active",
                  "打折后可发布": "release_on_discount", "原因": "reason", "备注": "note"}


def to_bool(v):
    """是/否 → True/False；空或无法识别 → None。"""
    if v is None or (not isinstance(v, bool) and pd.isna(v)):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().upper()
    return True if s in YES else False if s in NO else None


def _fetch_channel_product_ids(df: pd.DataFrame) -> pd.Series:
    """code_key → 鲸芽渠道产品ID（库存表 channel_product_id，多个用逗号分隔）。"""
    from common.pricing.discount_status import fetch_discount_status
    has_brand = df["brand"].notna() & df["brand"].astype(str).str.strip().ne("")
    by_brand = df[has_brand].groupby(df["brand"].str.strip().str.lower())["code_key"].apply(list).to_dict()
    status = fetch_discount_status(by_brand)
    return status.set_index("code_key")["channel_product_ids"]


def _fetch_store_item_ids(code_keys: list[str]) -> pd.DataFrame:
    """一行一个 code_key，列为「淘宝商品ID@店铺」（catalog_items.current_item_id，按 ACTIVE_STORES）。"""
    import psycopg2
    from cfg.db_config import PGSQL_CONFIG
    from analytics.pipeline.store_config import get_active_stores

    stores = get_active_stores()
    cols = [f"淘宝商品ID@{s.folder}" for s in stores]
    if not code_keys:
        return pd.DataFrame(columns=["code_key", *cols])
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        ids = pd.read_sql("""
            SELECT UPPER(TRIM(product_code)) AS code_key, store_name,
                   STRING_AGG(DISTINCT current_item_id::text, ',') AS item_ids
            FROM catalog_items
            WHERE store_name = ANY(%s) AND UPPER(TRIM(product_code)) = ANY(%s)
            GROUP BY 1, 2;
        """, conn, params=([s.store_name for s in stores], code_keys))
    finally:
        conn.close()
    label = {s.store_name: f"淘宝商品ID@{s.folder}" for s in stores}
    wide = ids.assign(store=ids["store_name"].map(label)) \
        .pivot(index="code_key", columns="store", values="item_ids")
    return wide.reindex(columns=cols).reset_index()


def export_to_excel(path: Path) -> Path:
    df = read_blocklist()
    out = df.reindex(columns=["code_key", *EXPORT_COLUMNS]).copy()
    for c in BOOL_COLUMNS:
        out[c] = out[c].map(lambda v: "" if v is None or pd.isna(v) else ("是" if v else "否"))

    # 鲸芽渠道产品ID + 各店淘宝商品ID，插在「品牌」后面，便于去鲸芽/淘宝集中处理
    out.insert(3, "鲸芽渠道产品ID", out["code_key"].map(_fetch_channel_product_ids(df)))
    stores = _fetch_store_item_ids(out["code_key"].tolist())
    store_cols = [c for c in stores.columns if c != "code_key"]
    out = out.merge(stores, on="code_key", how="left")
    head = ["product_code", "brand", "鲸芽渠道产品ID", *store_cols]
    out = out[[*head, *[c for c in out.columns if c not in head and c != "code_key"]]]
    out = out.rename(columns=EXPORT_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="blocklist")
        ws = writer.sheets["blocklist"]
        ws.freeze_panes = "B2"
        widths = {"商品编码": 18, "品牌": 10, "鲸芽渠道产品ID": 16, "启用": 6, "打折后可发布": 12, "原因": 60, "备注": 20}
        for i, name in enumerate(out.columns, start=1):
            w = widths.get(name, 17 if name.startswith("淘宝商品ID@") else 13)
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    return path


def read_import_excel(path: Path) -> pd.DataFrame:
    """读取导入 Excel，返回英文字段名 DataFrame（只含 IMPORT_COLUMNS 中存在的列）。"""
    df = pd.read_excel(path, dtype=str)
    if "商品编码" not in df.columns:
        raise ValueError(f"❌ Excel 缺少「商品编码」列：{path}")
    df = df[[c for c in IMPORT_COLUMNS if c in df.columns]].rename(columns=IMPORT_COLUMNS)
    df["product_code"] = df["product_code"].astype(str).str.strip()
    df = df[df["product_code"].ne("") & df["product_code"].ne("nan")]
    for c in ("is_active", "release_on_discount"):
        if c in df.columns:
            df[c] = df[c].map(to_bool)
    for c in ("brand", "reason", "note"):
        if c in df.columns:
            df[c] = df[c].where(df[c].notna() & df[c].astype(str).str.strip().ne(""), None)
    return df.drop_duplicates("product_code", keep="last")
