# -*- coding: utf-8 -*-
"""
Barbour 回填（严格：仅按 (product_code + size) 精确匹配最低价；不做任何忽略尺码兜底）
- 不依赖 barbour_supplier_map
- 每条 inventory (code+size) 只在 offers 同款同尺码里选最低有效价（有货优先→低价→最新）
- 匹配不到则不改该行（如需清零，可在末尾加一个可选 SQL）
- 计算人民币价：用 COALESCE(discount_price_gbp, source_price_gbp) 调用 calculate_jingya_prices
"""

from __future__ import annotations
from typing import List, Tuple, Iterable
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from config import BRAND_CONFIG
from common_taobao.core.price_utils import calculate_jingya_prices

# —— 尺码归一化：写死一份轻量规则，确保两边一致（不依赖外部包）
import re
import sys, inspect
def _clean_size(s: str) -> str:
    x = (s or "").strip().lower()
    x = re.sub(r"^uk[ \t]*", "", x)        # 去前缀 UK
    x = re.sub(r"(inch|in|cm)$", "", x)    # 去尾部单位
    x = re.sub(r"[ \t\./_-]+", "", x)      # 去常见分隔符
    x = x.replace("2xl", "xxl").replace("3xl", "xxxl")
    return x or "unknown"

def _ensure_price_columns(conn: Connection):
    conn.execute(text("""
        ALTER TABLE barbour_inventory
          ADD COLUMN IF NOT EXISTS jingya_untaxed_price   NUMERIC(12,2),
          ADD COLUMN IF NOT EXISTS taobao_store_price   NUMERIC(12,2),
          ADD COLUMN IF NOT EXISTS base_price_gbp     NUMERIC(10,2),
          ADD COLUMN IF NOT EXISTS exchange_rate_used NUMERIC(8,4)
    """))

def _num_or_none(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None

def _compute_rmb_prices(base_gbp):
    if base_gbp is None:
        return None, None
    untaxed, retail = calculate_jingya_prices(float(base_gbp))
    return _num_or_none(untaxed), _num_or_none(retail)

# ——— 临时表：逐条精确匹配需要的最小数据
SQL_CREATE_TMP = [
    text("""
        DROP TABLE IF EXISTS tmp_bi_exact;
        CREATE TEMP TABLE tmp_bi_exact(
            bi_id        INT,
            product_code VARCHAR(80),
            size_norm    VARCHAR(80)
        )
    """),
    text("""
        DROP TABLE IF EXISTS tmp_offer_exact;
        CREATE TEMP TABLE tmp_offer_exact(
            color_code   VARCHAR(80),
            size_norm    VARCHAR(80),
            site_name    VARCHAR(120),
            offer_url    TEXT,
            price_gbp    NUMERIC(10,2),
            original_price_gbp NUMERIC(10,2),
            discount_price_gbp NUMERIC(10,2),
            eff_price    NUMERIC(10,2),
            stock_count  INT,
            last_checked TIMESTAMP
        )
    """)
]
SQL_INDEX_TMP = [
    text("CREATE INDEX ON tmp_bi_exact(product_code, size_norm)"),
    text("CREATE INDEX ON tmp_offer_exact(color_code, size_norm)")
]

# —— 精确匹配：(code+size_norm) 选“有货优先→最低有效价→最新”
SQL_APPLY_BEST = text("""
    WITH candidates AS (
      SELECT color_code, size_norm, site_name, offer_url,
             price_gbp, original_price_gbp, discount_price_gbp,
             eff_price, stock_count, last_checked
      FROM tmp_offer_exact
      WHERE eff_price IS NOT NULL
    ),
    best AS (
      SELECT DISTINCT ON (color_code, size_norm)
             color_code, size_norm, site_name, offer_url,
             price_gbp, original_price_gbp, discount_price_gbp,
             eff_price, stock_count, last_checked
      FROM candidates
      ORDER BY color_code, size_norm,
               CASE WHEN COALESCE(stock_count,0) > 0 THEN 0 ELSE 1 END,
               eff_price ASC NULLS LAST,
               last_checked DESC
    )
    UPDATE barbour_inventory AS bi
    SET
      source_site          = b.site_name,
      source_offer_url     = b.offer_url,
      source_price_gbp     = b.price_gbp,
      original_price_gbp   = b.original_price_gbp,
      discount_price_gbp   = b.discount_price_gbp,
      stock_count          = COALESCE(b.stock_count, 0),
      product_url          = COALESCE(bi.product_url, b.offer_url),
      last_checked         = NOW()
    FROM tmp_bi_exact t
    JOIN best b
      ON b.color_code = t.product_code
     AND b.size_norm  = t.size_norm
    WHERE bi.id = t.bi_id
    RETURNING bi.id
""")

def backfill_barbour_inventory_single_supplier():
    """
    方案1：单一主供货商回填
    - 仅使用 barbour_supplier_map 中映射的站点(site_name)作为选源
    - 其它流程（有货优先→最低有效价→最新、RMB 价计算）与方案2一致
    """
    print(">>> MODE: SINGLE_SUPPLIER (via barbour_supplier_map)", file=sys.stderr)
    print(">>> LOADED FROM:", __file__, file=sys.stderr)

    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    engine = create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
    with engine.begin() as conn:
        _ensure_price_columns(conn)

        # 1) 建临时表（与方案2一致）
        for sql in SQL_CREATE_TMP:
            conn.execute(sql)

        # 2) 准备 tmp_bi_exact：只处理有尺码的行
        inv_rows = list(conn.execute(text("""
            SELECT id, product_code, size
            FROM barbour_inventory
            WHERE product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """)))
        bi_values: List[Tuple] = []
        for bi_id, code, size in inv_rows:
            szn = _clean_size(size)
            if szn and szn != "unknown":
                bi_values.append((bi_id, (code or "").strip(), szn))
        if bi_values:
            conn.exec_driver_sql(
                "INSERT INTO tmp_bi_exact(bi_id, product_code, size_norm) VALUES (%s,%s,%s)",
                bi_values
            )

        # 3) 准备 tmp_offer_exact：只取“映射站点”的 offers
        #    关键点：JOIN barbour_supplier_map 并按 site_name 精确限定
        off_rows = list(conn.execute(text("""
            SELECT o.product_code, o.size, o.site_name, o.offer_url,
                   o.price_gbp, o.original_price_gbp, o.sale_price_gbp,
                   o.stock_count, o.last_checked
            FROM barbour_offers o
            JOIN barbour_supplier_map m
              ON m.product_code = o.product_code
             AND lower(o.site_name) = lower(m.site_name)
            WHERE o.is_active = TRUE
              AND o.product_code IS NOT NULL AND o.product_code <> ''
              AND o.size IS NOT NULL AND o.size <> ''
        """)))
        off_values: List[Tuple] = []
        for code, size, site, url, price, original, sale, stock, ts in off_rows:
            szn = _clean_size(size)
            if not szn or szn == "unknown":
                continue
            eff = sale if sale is not None else price
            if eff is None:
                continue
            off_values.append(((code or "").strip(), szn, (site or "").strip(),
                               url, price, original, sale, eff, stock, ts))
        if off_values:
            conn.exec_driver_sql(
                """INSERT INTO tmp_offer_exact(color_code, size_norm, site_name, offer_url,
                                               price_gbp, original_price_gbp, discount_price_gbp,
                                               eff_price, stock_count, last_checked)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                off_values
            )

        # 4) 索引（与方案2一致）
        for sql in SQL_INDEX_TMP:
            conn.execute(sql)

        # 5) 精确匹配 & 写回（与方案2一致：有货优先→最低有效价→最新）
        rs = conn.execute(SQL_APPLY_BEST)
        hit_ids = [r[0] for r in (rs.fetchall() or [])]

        # 6) 计算人民币价（与方案2一致）
        if hit_ids:
            base_rows = list(conn.execute(text("""
                SELECT id, COALESCE(discount_price_gbp, source_price_gbp) AS base_gbp
                FROM barbour_inventory WHERE id = ANY(:ids)
            """), {"ids": hit_ids}).mappings())
            payload = []
            for r in base_rows:
                base_gbp = r["base_gbp"]

                discount = BRAND_CONFIG["barbour"].get("TAOBAO_STORE_DISCOUNT", 1.0)

                jy, tb = _compute_rmb_prices(base_gbp)
                if tb is not None:
                    tb = round(tb * discount, 2)   # 👈 淘宝店铺价按配置折扣
                
                
                payload.append({
                    "bi_id": r["id"],
                    "base_price_gbp": _num_or_none(base_gbp),
                    "exchange_rate_used": None,
                    "jingya_untaxed_price": jy,
                    "taobao_store_price": tb
                })


            if payload:
                conn.execute(text("""
                    UPDATE barbour_inventory
                    SET base_price_gbp   = :base_price_gbp,
                        exchange_rate_used = :exchange_rate_used,
                        jingya_untaxed_price = :jingya_untaxed_price,
                        taobao_store_price = :taobao_store_price
                    WHERE id = :bi_id
                """), payload)

    print(f"✅ 单一主供应商回填完成：命中 {len(hit_ids)} 行。")


def backfill_barbour_inventory_mapped_only():
    print(">>> MODE: EXACT_ONLY", file=sys.stderr)
    print(">>> LOADED FROM:", __file__, file=sys.stderr)
    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    engine = create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
    with engine.begin() as conn:
        _ensure_price_columns(conn)

        # 临时表
        for sql in SQL_CREATE_TMP: conn.execute(sql)

        # 1) 准备 tmp_bi_exact：只要 size 不空的 inventory 行
        inv_rows = list(conn.execute(text("""
            SELECT id, product_code, size
            FROM barbour_inventory
            WHERE product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """)))
        bi_values: List[Tuple] = []
        for bi_id, code, size in inv_rows:
            szn = _clean_size(size)
            if szn and szn != "unknown":
                bi_values.append((bi_id, (code or "").strip(), szn))
        if bi_values:
            conn.exec_driver_sql(
                "INSERT INTO tmp_bi_exact(bi_id, product_code, size_norm) VALUES (%s,%s,%s)",
                bi_values
            )

        # 2) 准备 tmp_offer_exact：同款同尺码的全部 offers（不看映射）
        off_rows = list(conn.execute(text("""
            SELECT product_code, size, site_name, offer_url,
                   price_gbp, original_price_gbp, sale_price_gbp,
                   stock_count, last_checked
            FROM barbour_offers
            WHERE is_active = TRUE
              AND product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """)))
        off_values: List[Tuple] = []
        for code, size, site, url, price, original, sale, stock, ts in off_rows:
            szn = _clean_size(size)
            if not szn or szn == "unknown":
                continue
            eff = sale if sale is not None else price
            if eff is None:
                continue
            off_values.append(((code or "").strip(), szn, (site or "").strip(),
                               url, price, original, sale, eff, stock, ts))
        if off_values:
            conn.exec_driver_sql(
                """INSERT INTO tmp_offer_exact(color_code, size_norm, site_name, offer_url,
                                               price_gbp, original_price_gbp, discount_price_gbp,
                                               eff_price, stock_count, last_checked)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                off_values
            )

        # 建索引
        for sql in SQL_INDEX_TMP: conn.execute(sql)

        # 3) 精确匹配并写回
        rs = conn.execute(SQL_APPLY_BEST)
        hit_ids = [r[0] for r in (rs.fetchall() or [])]

        # 4) 计算人民币价（只对命中的行）
        if hit_ids:
            base_rows = list(conn.execute(text("""
                SELECT id, COALESCE(discount_price_gbp, source_price_gbp) AS base_gbp
                FROM barbour_inventory WHERE id = ANY(:ids)
            """), {"ids": hit_ids}).mappings())
            payload = []
            for r in base_rows:
                base_gbp = r["base_gbp"]


                discount = BRAND_CONFIG["barbour"].get("TAOBAO_STORE_DISCOUNT", 1.0)
                jy, tb = _compute_rmb_prices(base_gbp)

                if tb is not None:
                    tb = round(tb * discount, 2)   # 👈 淘宝店铺价按配置折扣
                payload.append({
                    "bi_id": r["id"],
                    "base_price_gbp": _num_or_none(base_gbp),
                    "exchange_rate_used": None,
                    "jingya_untaxed_price": jy,
                    "taobao_store_price": tb
                })
            if payload:
                conn.execute(text("""
                    UPDATE barbour_inventory
                    SET base_price_gbp   = :base_price_gbp,
                        exchange_rate_used = :exchange_rate_used,
                        jingya_untaxed_price = :jingya_untaxed_price,
                        taobao_store_price = :taobao_store_price
                    WHERE id = :bi_id
                """), payload)

    print(f"✅ 精确匹配完成：命中 {len(hit_ids)} 行。")

if __name__ == "__main__":
    backfill_barbour_inventory_mapped_only()
