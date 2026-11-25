# -*- coding: utf-8 -*-
"""
商品（渠道产品ID / 商品编码）→ 各店铺淘宝商品ID。

库存表里没有淘宝商品ID，按下面顺序找，前一步找不到才用后一步：
  1. catalog_items（analytics/pipeline/run_import_data 导入）：商家编码 = 商品编码
  2. run_import_data 读取的店铺 itemList Excel：sku规格里含该商品编码
     （多色合并的宝贝，商家编码为空或只写一个颜色，catalog_items 里对不上）
  3. 同一渠道产品ID 下的其他商品编码，按 1、2 能找到的淘宝商品ID

店铺上下架后先重跑 run_import_data，映射才是最新的。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import psycopg2

from cfg.db_config import BRAND_TABLE, PGSQL_CONFIG
from creative.product_source import ProductInfo

MATCH_CATALOG, MATCH_SKU, MATCH_CHANNEL = 1, 2, 3


def _key(code) -> str:
    return str(code or "").strip().upper()


@dataclass
class StoreItems:
    """一个店铺的映射：商品编码（大写）→ 淘宝商品ID 列表、匹配方式。"""
    folder: str
    ids: dict[str, list[str]] = field(default_factory=dict)
    match: dict[str, int] = field(default_factory=dict)

    def get(self, code: str) -> list[str]:
        return self.ids.get(_key(code), [])


def _active_stores(stores: list[str] | None):
    from analytics.pipeline.store_config import get_active_stores
    active = get_active_stores()
    unknown = set(stores or []) - {s.folder for s in active}
    if unknown:
        raise ValueError(f"❌ 未启用的店铺：{', '.join(unknown)}，可选：{', '.join(s.folder for s in active)}")
    return [s for s in active if not stores or s.folder in stores]


def _channel_codes(cur, products: list[ProductInfo]) -> dict[tuple[str, str], list[str]]:
    """(品牌, 渠道产品ID) → 该渠道产品下的全部商品编码。"""
    out: dict[tuple[str, str], list[str]] = {}
    for brand in {p.brand for p in products}:
        channels = list({p.channel_product_id for p in products if p.brand == brand and p.channel_product_id})
        cur.execute(f"SELECT DISTINCT TRIM(channel_product_id), UPPER(TRIM(product_code)) FROM {BRAND_TABLE[brand]} "
                    f"WHERE TRIM(channel_product_id) = ANY(%s) ORDER BY 1, 2", (channels,))
        for channel, code in cur.fetchall():
            out.setdefault((brand, channel), []).append(code)
    return out


def _catalog_ids(cur, store_name: str) -> dict[str, list[str]]:
    cur.execute("SELECT UPPER(TRIM(product_code)), current_item_id::text FROM catalog_items "
                "WHERE store_name = %s AND TRIM(COALESCE(product_code, '')) <> '' AND current_item_id IS NOT NULL "
                "ORDER BY 2 DESC", (store_name,))
    out: dict[str, list[str]] = {}
    for code, item_id in cur.fetchall():
        out.setdefault(code, []).append(item_id)
    return out


def _sku_ids(catalog_dir: Path, wanted: set[str]) -> dict[str, list[str]]:
    """itemList Excel：宝贝ID 只写在每个宝贝的第一行，其余 SKU 行为空，需要向下填充。"""
    out: dict[str, list[str]] = {}
    for f in sorted(Path(catalog_dir).glob("*.xlsx")):
        df = pd.read_excel(f, dtype=str)
        if not {"宝贝ID", "sku规格"} <= set(df.columns):
            continue
        item_ids = df["宝贝ID"].ffill()
        for item_id, spec in zip(item_ids, df["sku规格"]):
            if pd.isna(item_id) or pd.isna(spec):
                continue
            for token in str(spec).split(","):
                code = _key(token)
                if code in wanted and item_id not in out.setdefault(code, []):
                    out[code].append(item_id)
    return out


def build_store_items(products: list[ProductInfo], stores: list[str] | None = None) -> list[StoreItems]:
    """stores: 店铺目录名（同 store_config.ACTIVE_STORES），None = 全部启用的店铺。"""
    result = []
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            channel_codes = _channel_codes(cur, products)
            siblings = {_key(p.product_code): channel_codes.get((p.brand, p.channel_product_id), []) for p in products}
            for store in _active_stores(stores):
                catalog = _catalog_ids(cur, store.store_name)
                if not catalog:
                    print(f"⚠️ [{store.folder}] catalog_items 里没有该店数据，请先运行 analytics/pipeline/run_import_data.py")
                missing = {c for c in siblings if c not in catalog}
                wanted = missing | {s for c in missing for s in siblings[c] if s not in catalog}
                sku = _sku_ids(store.catalog_dir, wanted) if wanted else {}
                si = StoreItems(store.folder)
                for code in siblings:
                    found, how = catalog.get(code), MATCH_CATALOG
                    if not found:
                        found, how = sku.get(code), MATCH_SKU
                    if not found:
                        found = [i for s in siblings[code] for i in catalog.get(s) or sku.get(s) or []]
                        how = MATCH_CHANNEL
                    if found:
                        si.ids[code] = list(dict.fromkeys(found))
                        si.match[code] = how
                result.append(si)
    finally:
        conn.close()
    return result
