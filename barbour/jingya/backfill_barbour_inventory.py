# -*- coding: utf-8 -*-
"""
将 barbour_products / offers 的信息回填到 barbour_inventory。
匹配键：barbour_inventory.product_code = color_code 且 size 一致。

步骤：
  1) products → 回填 title / description / gender / category
  2A) offers(可下单&有货) → 选源/价格/库存（优先）
  2B) offers(任意) → 对仍未命中的 SKU 兜底选源/价格（库存置 0）

需要：BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
"""

import psycopg2
from config import BRAND_CONFIG

# 有货时写入的库存数（你淘宝端常用“有货上3件”）
STOCK_WHEN_AVAILABLE = 3

# 站点优先级（越靠前越优先；可按你的渠道调整）
SITE_PRIORITY = [
    'Outdoor and Country', 'Allweathers', 'Philip Morris Direct', 'Philip Morris',
    'Country Attire', 'Scotts', 'Aphrodite', 'Tessuti', 'END.'
]

# 生成 CASE WHEN 的 SQL 片段
def build_site_rank_case():
    if not SITE_PRIORITY:
        return "CASE WHEN 1=1 THEN 999 END"
    parts = []
    for i, name in enumerate(SITE_PRIORITY):
        safe = name.replace("'", "''")
        parts.append(f"WHEN o.site_name = '{safe}' THEN {i}")
    parts.append("ELSE 999")
    return "CASE " + " ".join(parts) + " END"

def backfill_barbour_inventory():
    dsn = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    conn = psycopg2.connect(**dsn)
    with conn:
        with conn.cursor() as cur:

            # ---------- Step 1: products → inventory ----------
            # 注意 style_category 长度为 VARCHAR(20)，避免溢出：LEFT(..., 20)
            cur.execute("""
                UPDATE barbour_inventory AS bi
                SET
                    product_title       = p.title,
                    product_description = p.product_description,
                    gender              = COALESCE(bi.gender, p.gender),
                    style_category      = LEFT(p.category, 20),
                    last_checked        = NOW()
                FROM barbour_products AS p
                WHERE p.color_code = bi.product_code
                  AND p.size       = bi.size;
            """)
            print(f"Step1 回填基础信息：更新 {cur.rowcount} 行")

            # ---------- Step 2A: offers(可下单&有货) → inventory ----------
            # “可下单且有货”定义：can_order = TRUE 且 stock_status ∈ {NULL, 'In Stock', '有货'}
            # 选择规则：站点优先级 → 价格低 → 抓取时间新
            site_rank_case = build_site_rank_case()
            cur.execute(f"""
                WITH avail AS (
                  SELECT
                    o.color_code,
                    o.size,
                    o.site_name,
                    o.offer_url,
                    o.price_gbp,
                    {site_rank_case} AS site_rank,
                    o.last_checked
                  FROM offers AS o
                  WHERE o.can_order IS TRUE
                    AND (
                      o.stock_status ILIKE 'in stock'
                      OR o.stock_status = '有货'
                      OR o.stock_status IS NULL
                    )
                ),
                best_avail AS (
                  -- DISTINCT ON：每个 (color_code,size) 选一条最佳记录
                  SELECT DISTINCT ON (color_code, size)
                    color_code, size, site_name, offer_url, price_gbp
                  FROM avail
                  ORDER BY color_code, size, site_rank ASC,
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
                FROM best_avail AS b
                WHERE b.color_code = bi.product_code
                  AND b.size       = bi.size;
            """, (STOCK_WHEN_AVAILABLE,))
            print(f"Step2A 可下单有货选源：更新 {cur.rowcount} 行")

            # ---------- Step 2B: offers(任意) 兜底 → inventory ----------
            # 仅更新“尚未选到可下单有货”的 SKU（即 Step2A 未覆盖的行）
            cur.execute(f"""
                WITH any_offer AS (
                  SELECT
                    o.color_code,
                    o.size,
                    o.site_name,
                    o.offer_url,
                    o.price_gbp,
                    {site_rank_case} AS site_rank,
                    o.last_checked
                  FROM offers AS o
                ),
                best_any AS (
                  SELECT DISTINCT ON (color_code, size)
                    color_code, size, site_name, offer_url, price_gbp
                  FROM any_offer
                  ORDER BY color_code, size, site_rank ASC,
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
                FROM best_any AS b
                WHERE b.color_code = bi.product_code
                  AND b.size       = bi.size
                  AND bi.source_site IS NULL;   -- 只兜底未命中的
            """)
            print(f"Step2B 不可下单兜底选源：更新 {cur.rowcount} 行")

    print("✅ 回填完成：products → inventory；offers → inventory（含择优与兜底）")

if __name__ == "__main__":
    backfill_barbour_inventory()
