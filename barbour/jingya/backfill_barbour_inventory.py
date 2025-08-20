# -*- coding: utf-8 -*-
"""
将 barbour_products / offers 的信息按“尺码已归一化”的方式回填到 barbour_inventory。
"""

from __future__ import annotations
import psycopg2
from psycopg2.extras import execute_values
from config import BRAND_CONFIG
from common_taobao.size_utils import clean_size_for_barbour  # 复用你现成的清洗逻辑

STOCK_WHEN_AVAILABLE = 3

SITE_PRIORITY = [
    'Outdoor and Country', 'Allweathers', 'Philip Morris Direct', 'Philip Morris',
    'Country Attire', 'Scotts', 'Aphrodite', 'Tessuti', 'END.'
]

def _site_rank_case_sql(alias: str = "tpo") -> str:
    if not SITE_PRIORITY:
        return "CASE WHEN 1=1 THEN 999 END"
    parts = []
    for i, name in enumerate(SITE_PRIORITY):
        safe = name.replace("'", "''")
        parts.append(f"WHEN {alias}.site_name = '{safe}' THEN {i}")
    parts.append("ELSE 999")
    return "CASE " + " ".join(parts) + " END"

def backfill_barbour_inventory():
    dsn = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    conn = psycopg2.connect(**dsn)
    with conn:
        with conn.cursor() as cur:
            # 1) 拉取三张表
            cur.execute("SELECT id, product_code, size FROM barbour_inventory;")
            inv_rows = cur.fetchall()
            cur.execute("""SELECT id, color_code, size, title, product_description, gender, category
                           FROM barbour_products;""")
            prod_rows = cur.fetchall()
            cur.execute("""SELECT id, color_code, size, site_name, offer_url, price_gbp,
                                  stock_status, can_order, last_checked
                           FROM offers;""")
            offer_rows = cur.fetchall()

            # 2) 临时表
            cur.execute("DROP TABLE IF EXISTS tmp_bi;")
            cur.execute("DROP TABLE IF EXISTS tmp_p;")
            cur.execute("DROP TABLE IF EXISTS tmp_o;")

            cur.execute("""
                CREATE TEMP TABLE tmp_bi (
                  bi_id INT PRIMARY KEY,
                  product_code VARCHAR(200),
                  size_norm VARCHAR(32)
                ) ON COMMIT DROP;
            """)
            cur.execute("""
                CREATE TEMP TABLE tmp_p (
                  p_id INT PRIMARY KEY,
                  color_code VARCHAR(50),
                  size_norm VARCHAR(32),
                  title TEXT,
                  product_description TEXT,
                  gender VARCHAR(20),
                  category VARCHAR(100)
                ) ON COMMIT DROP;
            """)
            cur.execute("""
                CREATE TEMP TABLE tmp_o (
                  o_id INT PRIMARY KEY,
                  color_code VARCHAR(50),
                  size_norm VARCHAR(32),
                  site_name VARCHAR(100),
                  offer_url TEXT,
                  price_gbp NUMERIC(10,2),
                  stock_status VARCHAR(50),
                  can_order BOOLEAN,
                  last_checked TIMESTAMP
                ) ON COMMIT DROP;
            """)

            inv_payload = [(i, code, clean_size_for_barbour(sz)) for (i, code, sz) in inv_rows]
            execute_values(cur,
                "INSERT INTO tmp_bi (bi_id, product_code, size_norm) VALUES %s",
                inv_payload, page_size=1000)

            prod_payload = [
                (i, code, clean_size_for_barbour(sz), title, desc, gd, cat)
                for (i, code, sz, title, desc, gd, cat) in prod_rows
            ]
            execute_values(cur,
                "INSERT INTO tmp_p (p_id, color_code, size_norm, title, product_description, gender, category) VALUES %s",
                prod_payload, page_size=1000)

            offer_payload = [
                (i, code, clean_size_for_barbour(sz), site, url, price, stock, can, ts)
                for (i, code, sz, site, url, price, stock, can, ts) in offer_rows
            ]
            execute_values(cur,
                "INSERT INTO tmp_o (o_id, color_code, size_norm, site_name, offer_url, price_gbp, stock_status, can_order, last_checked) VALUES %s",
                offer_payload, page_size=1000)

            # 3) Step 1：基础信息
            cur.execute("""
                UPDATE barbour_inventory AS bi
                SET
                    product_title       = p.title,
                    product_description = p.product_description,
                    gender              = COALESCE(bi.gender, p.gender),
                    style_category      = LEFT(p.category, 20),
                    last_checked        = NOW()
                FROM tmp_bi tbi
                JOIN tmp_p tp
                  ON tp.color_code = tbi.product_code
                 AND tp.size_norm  = tbi.size_norm
                JOIN barbour_products p
                  ON p.id = tp.p_id
                WHERE bi.id = tbi.bi_id
                  AND tbi.size_norm <> 'Unknown';
            """)
            print(f"Step1 回填基础信息：更新 {cur.rowcount} 行")

            # 4) Step 2A：可下单有货择优
            site_rank_case = _site_rank_case_sql("tpo")
            cur.execute(f"""
                WITH avail AS (
                    SELECT
                        tpo.color_code,
                        tpo.size_norm,
                        tpo.site_name,
                        tpo.offer_url,
                        tpo.price_gbp,
                        {site_rank_case} AS site_rank,
                        tpo.last_checked
                    FROM tmp_o tpo
                    WHERE tpo.can_order IS TRUE
                      AND (
                           tpo.stock_status ILIKE 'in stock'
                        OR tpo.stock_status = '有货'
                        OR tpo.stock_status IS NULL
                      )
                ),
                best_avail AS (
                    SELECT DISTINCT ON (color_code, size_norm)
                        color_code, size_norm, site_name, offer_url, price_gbp
                    FROM avail
                    ORDER BY color_code, size_norm, site_rank ASC,
                             price_gbp NULLS LAST, last_checked DESC
                )
                UPDATE barbour_inventory AS bi
                SET
                    source_site         = b.site_name,
                    source_offer_url    = b.offer_url,
                    source_price_gbp    = b.price_gbp,
                    discount_price_gbp  = b.price_gbp,
                    stock_count         = %s,
                    last_checked        = NOW()
                FROM tmp_bi tbi
                JOIN best_avail b
                  ON b.color_code = tbi.product_code
                 AND b.size_norm  = tbi.size_norm
                WHERE bi.id = tbi.bi_id
                  AND tbi.size_norm <> 'Unknown';
            """, (STOCK_WHEN_AVAILABLE,))
            print(f"Step2A 可下单有货选源：更新 {cur.rowcount} 行")

            # 5) Step 2B：任意报价兜底
            cur.execute(f"""
                WITH any_offer AS (
                    SELECT
                        tpo.color_code,
                        tpo.size_norm,
                        tpo.site_name,
                        tpo.offer_url,
                        tpo.price_gbp,
                        {site_rank_case} AS site_rank,
                        tpo.last_checked
                    FROM tmp_o tpo
                ),
                best_any AS (
                    SELECT DISTINCT ON (color_code, size_norm)
                        color_code, size_norm, site_name, offer_url, price_gbp
                    FROM any_offer
                    ORDER BY color_code, size_norm, site_rank ASC,
                             price_gbp NULLS LAST, last_checked DESC
                )
                UPDATE barbour_inventory AS bi
                SET
                    source_site         = b.site_name,
                    source_offer_url    = b.offer_url,
                    source_price_gbp    = b.price_gbp,
                    discount_price_gbp  = b.price_gbp,
                    stock_count         = 0,
                    last_checked        = NOW()
                FROM tmp_bi tbi
                JOIN best_any b
                  ON b.color_code = tbi.product_code
                 AND b.size_norm  = tbi.size_norm
                WHERE bi.id = tbi.bi_id
                  AND bi.source_site IS NULL
                  AND tbi.size_norm <> 'Unknown';
            """)
            print(f"Step2B 不可下单兜底选源：更新 {cur.rowcount} 行")

    print("✅ 回填完成（尺码已统一归一化，2XL/XXL、UK1 等可正确对齐）。")

if __name__ == "__main__":
    backfill_barbour_inventory()
