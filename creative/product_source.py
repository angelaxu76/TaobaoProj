# -*- coding: utf-8 -*-
"""
商品资料读取：数据库或 TXT → ProductInfo（一个商品编码一条）。

数据库是默认来源：TXT 的名称/描述/材质/特征在导入时已全部写入库存表，
而 TXT 目录会被流水线备份清空。Barbour 的资料来自 barbour_products。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg2

from cfg.db_config import BRAND_TABLE, PGSQL_CONFIG
from common.product.color_utils import to_color_cn

_EMPTY = {"", "no data", "none", "n/a", "null"}


def _clean(v) -> str:
    s = " ".join(re.sub(r"</?(?:br|li|p|ul)\s*/?>", " ", str(v or "")).split())
    return "" if s.lower() in _EMPTY else s


@dataclass
class ProductInfo:
    brand: str
    product_code: str
    title: str = ""
    description: str = ""
    gender: str = ""
    style_category: str = ""
    color_cn: str = ""
    material: str = ""
    feature: str = ""
    url: str = ""
    channel_product_id: str = ""

    @property
    def evidence(self) -> str:
        """英文商品资料全文，用于事实校验。"""
        return " ".join([self.title, self.description, self.material, self.feature, self.style_category]).lower()

    @property
    def has_detail(self) -> bool:
        return bool(self.title)

    @property
    def source_hash(self) -> str:
        raw = "|".join([self.title, self.description, self.material, self.feature, self.color_cn, self.gender])
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _build(brand: str, row: dict) -> ProductInfo:
    return ProductInfo(brand=brand, **{k: _clean(v) for k, v in row.items()})


_GENERIC_SQL = """
    SELECT product_code, MAX(product_title) AS title, MAX(product_description) AS description,
           MAX(gender) AS gender, MAX(style_category) AS style_category, MAX(color) AS color_cn,
           MAX(product_material) AS material, MAX(feature) AS feature, MAX(product_url) AS url,
           MAX(channel_product_id) AS channel_product_id
    FROM {table} {where}
    GROUP BY product_code ORDER BY product_code
"""

# barbour_inventory 没有标题/描述，取 barbour_products 中 source_rank 最小（最可信）的一条
_BARBOUR_SQL = """
    WITH inv AS (
        SELECT product_code, MAX(channel_product_id) AS channel_product_id, MAX(product_url) AS url
        FROM {table} {where} GROUP BY product_code
    ), p AS (
        SELECT DISTINCT ON (product_code) product_code, style_name, title, product_description, gender, category, color
        FROM barbour_products
        ORDER BY product_code, source_rank NULLS LAST, LENGTH(COALESCE(product_description, '')) DESC, id
    )
    SELECT inv.product_code, COALESCE(NULLIF(p.title, ''), p.style_name) AS title, p.product_description AS description,
           p.gender, p.category AS style_category, p.color AS color_cn, NULL AS material, NULL AS feature,
           inv.url, inv.channel_product_id
    FROM inv LEFT JOIN p ON p.product_code = inv.product_code ORDER BY inv.product_code
"""


def load_products_from_db(brand: str, scope: str = "published", codes: list[str] | None = None) -> list[ProductInfo]:
    """
    scope: published = 已发布到鲸芽；in_stock = 有库存；all = 全部。
    codes: 指定商品编码或渠道产品ID（给了就忽略 scope）。
    """
    brand = brand.lower().strip()
    if brand not in BRAND_TABLE:
        raise ValueError(f"❌ 不支持的品牌：{brand}，可选：{', '.join(BRAND_TABLE)}")
    params: list = []
    if codes is not None:
        keys = [str(c).strip().upper() for c in codes if str(c).strip()]
        where = "WHERE UPPER(TRIM(product_code)) = ANY(%s) OR TRIM(channel_product_id) = ANY(%s)"
        params = [keys, keys]
    elif scope == "published":
        where = "WHERE is_published"
    elif scope == "in_stock":
        where = "WHERE stock_count > 0"
    elif scope == "all":
        where = ""
    else:
        raise ValueError(f"❌ scope 只能是 published / in_stock / all：{scope}")

    sql = _BARBOUR_SQL if brand == "barbour" else _GENERIC_SQL
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.format(table=BRAND_TABLE[brand], where=where), params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    products = [_build(brand, r) for r in rows if _clean(r["product_code"])]
    if brand == "barbour":
        for p in products:
            p.color_cn = to_color_cn(p.color_cn, p.title)
    return products


_TXT_FIELDS = {
    "Product Code": "product_code", "Product Name": "title", "Product Description": "description",
    "Product Gender": "gender", "Style Category": "style_category", "Product Color": "color_cn",
    "Product Material": "material", "Feature": "feature", "Source URL": "url", "Product URL": "url",
}


def load_product_from_txt(brand: str, path: Path) -> ProductInfo | None:
    row: dict = {}
    for line in Path(path).read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        key, sep, val = line.partition(":")
        field = _TXT_FIELDS.get(key.strip())
        if sep and field and field not in row:
            row[field] = val
    if not _clean(row.get("product_code")):
        return None
    p = _build(brand, row)
    p.color_cn = to_color_cn(p.color_cn, p.title)
    return p


def load_products_from_txt(brand: str, txt_dir: Path | None = None,
                           codes: list[str] | None = None) -> list[ProductInfo]:
    from config import BRAND_CONFIG
    brand = brand.lower().strip()
    txt_dir = Path(txt_dir or BRAND_CONFIG[brand]["TXT_DIR"])
    if not txt_dir.is_dir():
        raise FileNotFoundError(f"❌ TXT 目录不存在：{txt_dir}")
    items = [load_product_from_txt(brand, f) for f in sorted(txt_dir.glob("*.txt"))]
    items = [p for p in items if p]
    if codes is not None:
        keys = {str(c).strip().upper() for c in codes}
        items = [p for p in items if p.product_code.upper() in keys]
    return items


def load_products(brand: str, source: str = "db", scope: str = "published",
                  codes: list[str] | None = None, txt_dir: Path | None = None) -> list[ProductInfo]:
    if source == "db":
        return load_products_from_db(brand, scope, codes)
    if source == "txt":
        return load_products_from_txt(brand, txt_dir, codes)
    raise ValueError(f"❌ source 只能是 db / txt：{source}")
