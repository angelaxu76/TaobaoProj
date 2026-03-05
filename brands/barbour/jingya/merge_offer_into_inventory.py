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
from common.pricing.price_utils import calculate_jingya_prices

# —— 尺码归一化：写死一份轻量规则，确保两边一致（不依赖外部包）
import re
import sys, inspect


from sqlalchemy import create_engine, text
import pandas as pd
from config import BRAND_CONFIG
from brands.barbour.core.site_utils import canonical_site

def merge_band_stock_into_inventory(band_ratio: float = 0.10, size_threshold: int = 1):
    """
    在 barbour_inventory 已经回填完“主供货商价格”的前提下：
    - 以 barbour_supplier_map 中映射的站点为基准，取该站点的折后价作为 best_base_price
    - 找出同一 product_code 下，折后价 <= best_base_price * (1 + band_ratio) 的所有站点
    - 用这些站点的库存做“并集”：任一站点有货，该尺码就视为有货（stock_count=3，否则=0）
    - 只改 barbour_inventory.stock_count，不动价格字段
    """
    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    eng = create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )

    SQL_AGG = text("""
    WITH agg AS (
      SELECT
        product_code,
        site_name,
        SUM(CASE WHEN COALESCE(stock_count,0) > 0 THEN 1 ELSE 0 END) AS sizes_in_stock,
        MIN(COALESCE(NULLIF(sale_price_gbp,0), NULLIF(price_gbp,0), original_price_gbp))
            FILTER (WHERE COALESCE(stock_count,0) > 0)               AS min_eff_price,
        MAX(last_checked)                                            AS latest
      FROM barbour_offers
      WHERE is_active = TRUE
        AND product_code IS NOT NULL AND product_code <> ''
        AND site_name IS NOT NULL AND site_name <> ''
      GROUP BY product_code, site_name
    )
    SELECT * FROM agg
    """)

    with eng.begin() as conn:
        # 1) 读取当前映射（最佳供货商）
        map_df = pd.read_sql("SELECT product_code, site_name FROM barbour_supplier_map", conn)
        map_df["site_name"] = map_df["site_name"].map(lambda s: canonical_site(s) or s)

        # 2) 读取各站点聚合后的“尺码数 + 折后最低价”
        agg_df = pd.read_sql(SQL_AGG, conn)
        agg_df["site_name"] = agg_df["site_name"].map(lambda s: canonical_site(s) or s)

        # 合并得到每个 product_code 对应的 best_base_price
        cur_df = map_df.merge(
            agg_df.rename(columns={
                "sizes_in_stock": "cur_sizes_in_stock",
                "min_eff_price": "cur_min_eff_price",
                "latest": "cur_latest",
            }),
            on=["product_code", "site_name"],
            how="left",
        )

        # 3) 读取全部 offers 的“尺码级库存”
        off_df = pd.read_sql("""
            SELECT product_code, size, site_name,
                   COALESCE(stock_count,0) AS stock_count
            FROM barbour_offers
            WHERE is_active = TRUE
              AND product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
              AND site_name IS NOT NULL AND site_name <> ''
        """, conn)
        off_df["site_name"] = off_df["site_name"].map(lambda s: canonical_site(s) or s)
        off_df["size_norm"] = off_df["size"].map(_clean_size)

        # 4) 读取 inventory 中的尺码行
        inv_df = pd.read_sql("""
            SELECT id, product_code, size
            FROM barbour_inventory
            WHERE product_code IS NOT NULL AND product_code <> ''
              AND size IS NOT NULL AND size <> ''
        """, conn)
        inv_df["size_norm"] = inv_df["size"].map(_clean_size)

        # 按商品分组，准备更新 payload
        agg_by_code = agg_df.groupby("product_code")
        off_by_code = off_df.groupby("product_code")
        inv_by_code = inv_df.groupby("product_code")

        updates = []

        for _, row in cur_df.iterrows():
            code = row["product_code"]
            best_price = row.get("cur_min_eff_price")
            if best_price is None or pd.isna(best_price):
                continue
            try:
                best_price = float(best_price)
            except Exception:
                continue
            # 该商品在 inventory/offers 中是否存在
            if code not in off_by_code.groups or code not in inv_by_code.groups:
                continue

            df_code_agg = agg_by_code.get_group(code)
            # 价格带内的所有站点（<= best_price * (1+band_ratio)）
            band_sites = df_code_agg[
                df_code_agg["min_eff_price"].notna()
                & (df_code_agg["min_eff_price"] <= best_price * (1.0 + band_ratio))
            ]["site_name"].unique().tolist()
            if not band_sites:
                continue

            df_off = off_by_code.get_group(code)
            df_off_band = df_off[df_off["site_name"].isin(band_sites)].copy()
            if df_off_band.empty:
                continue

            # 对 band 内所有站点做“尺码有无货并集”
            size_stock = (
                df_off_band
                .groupby("size_norm")["stock_count"]
                .apply(lambda s: int((s > 0).any()))
                .to_dict()
            )

            df_inv = inv_by_code.get_group(code)
            for _, inv_row in df_inv.iterrows():
                bi_id = inv_row["id"]
                szn = inv_row["size_norm"]
                has_stock = size_stock.get(szn, 0)
                new_stock = 3 if has_stock else 0
                updates.append({"bi_id": bi_id, "stock_count": new_stock})

        if updates:
            conn.execute(text("""
                UPDATE barbour_inventory
                SET stock_count = :stock_count
                WHERE id = :bi_id
            """), updates)

    print(f"✅ 价格带库存合并完成，更新 {len(updates)} 条 inventory 记录。")


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

import os
import pandas as pd
from sqlalchemy import create_engine, text
from config import BRAND_CONFIG
from common.pricing.price_utils import calculate_jingya_prices

def apply_fixed_prices_from_excel(
    xlsx_path: str,
    sheet_name: str | None = None,
    code_col: str = "product_code",
    source_price_col: str = "source_price_gbp",
    discount_price_col: str = "discount_price_gbp",
    also_set_original_price: bool = True,
    mark_source: bool = True,
    dry_run: bool = False,
):
    """
    从 Excel 读取固定价格清单，批量回填到 barbour_inventory（按 product_code 覆盖所有尺码行）。

    Excel 必需列（默认列名，可通过参数改）：
      - product_code
      - source_price_gbp
      - discount_price_gbp

    会更新的字段（默认）：
      - source_price_gbp
      - discount_price_gbp
      - original_price_gbp（可选：also_set_original_price=True 时设置为折扣价）
      - base_price_gbp（= COALESCE(discount_price_gbp, source_price_gbp)）
      - jingya_untaxed_price / taobao_store_price（由 calculate_jingya_prices 计算）
      - last_checked
      - （可选）source_site/source_offer_url 标记为 manual
    """

    if not xlsx_path or not os.path.exists(xlsx_path):
        print(f"ℹ️ 固定价格清单文件不存在，已跳过：{xlsx_path}")
        return

    cfg = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    engine = create_engine(
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )

    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

    # ✅ 兼容：sheet_name=None 时 pandas 返回 dict（所有 sheets）
    if isinstance(df, dict):
        if not df:
            raise ValueError("Excel 里没有任何 sheet。")
        # 默认取第一个 sheet
        df = next(iter(df.values()))

    df = df.rename(columns={
        code_col: "product_code",
        source_price_col: "source_price_gbp",
        discount_price_col: "discount_price_gbp",
    })

    # 基本清洗
    df["product_code"] = df["product_code"].astype(str).str.strip()
    df = df[df["product_code"].notna() & (df["product_code"] != "")]
    df["source_price_gbp"] = pd.to_numeric(df["source_price_gbp"], errors="coerce")
    df["discount_price_gbp"] = pd.to_numeric(df["discount_price_gbp"], errors="coerce")

    # base_gbp：后续用于 RMB 计算
    df["base_gbp"] = df["discount_price_gbp"].fillna(df["source_price_gbp"])

    # 计算 RMB 两个价
    discount = BRAND_CONFIG["barbour"].get("TAOBAO_STORE_DISCOUNT", 1.0)
    jy_list, tb_list = [], []
    for v in df["base_gbp"].tolist():
        if pd.isna(v) or v is None:
            jy_list.append(None)
            tb_list.append(None)
            continue
        untaxed, retail = calculate_jingya_prices(float(v))
        jy_list.append(round(float(untaxed), 2) if untaxed is not None else None)
        tb = round(float(retail) * float(discount), 2) if retail is not None else None
        tb_list.append(tb)

    df["jingya_untaxed_price"] = jy_list
    df["taobao_store_price"] = tb_list

    # 准备更新 payload
    src_tag = "manual_excel"
    offer_tag = f"excel:{os.path.basename(xlsx_path)}"
    payload = []
    for r in df.to_dict("records"):
        payload.append({
            "product_code": r["product_code"],
            "source_price_gbp": None if pd.isna(r["source_price_gbp"]) else float(r["source_price_gbp"]),
            "discount_price_gbp": None if pd.isna(r["discount_price_gbp"]) else float(r["discount_price_gbp"]),
            "original_price_gbp": None if (not also_set_original_price or pd.isna(r["discount_price_gbp"])) else float(r["discount_price_gbp"]),
            "base_price_gbp": None if pd.isna(r["base_gbp"]) else float(r["base_gbp"]),
            "jingya_untaxed_price": r["jingya_untaxed_price"],
            "taobao_store_price": r["taobao_store_price"],
            "source_site": src_tag,
            "source_offer_url": offer_tag,
        })

    if dry_run:
        print(f"[DryRun] 将覆盖 {len(payload)} 个 product_code 的 inventory 价格（所有尺码行）。示例前5行：")
        for x in payload[:5]:
            print(x)
        return

    with engine.begin() as conn:
        if mark_source:
            sql = text("""
                UPDATE barbour_inventory
                SET
                    source_price_gbp     = :source_price_gbp,
                    original_price_gbp   = COALESCE(:original_price_gbp, original_price_gbp),
                    discount_price_gbp   = :discount_price_gbp,
                    base_price_gbp       = :base_price_gbp,
                    jingya_untaxed_price = :jingya_untaxed_price,
                    taobao_store_price   = :taobao_store_price,
                    source_site          = :source_site,
                    source_offer_url     = :source_offer_url,
                    last_checked         = NOW()
                WHERE product_code = :product_code
            """)
        else:
            sql = text("""
                UPDATE barbour_inventory
                SET
                    source_price_gbp     = :source_price_gbp,
                    original_price_gbp   = COALESCE(:original_price_gbp, original_price_gbp),
                    discount_price_gbp   = :discount_price_gbp,
                    base_price_gbp       = :base_price_gbp,
                    jingya_untaxed_price = :jingya_untaxed_price,
                    taobao_store_price   = :taobao_store_price,
                    last_checked         = NOW()
                WHERE product_code = :product_code
            """)

        conn.execute(sql, payload)

    print(f"✅ 固定价格已回填到 barbour_inventory：{len(payload)} 个 product_code（覆盖所有尺码行）。")


if __name__ == "__main__":
    backfill_barbour_inventory_mapped_only()
