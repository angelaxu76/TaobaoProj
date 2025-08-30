# -*- coding: utf-8 -*-
"""
将 barbour_products / offers 的信息按“尺码已归一化”的方式回填到 barbour_inventory。
新增：支持“部分商家 / 部分编码前缀有折扣”的规则。
- source_price_gbp：保留原价（商家页面展示价 / 爬取价）
- discount_price_gbp：按规则计算后的折扣价（无匹配则等于原价）
"""

from __future__ import annotations
import re
from typing import List, Tuple, Optional, Dict, Any

import psycopg2
from psycopg2.extras import execute_values
from barbour.core.site_utils import canonical_site
from config import BRAND_CONFIG
from common_taobao.size_utils import clean_size_for_barbour  # 复用现成清洗逻辑


# ============ 可调参数 ============
STOCK_WHEN_AVAILABLE = 3

# 站点优先级（越靠前优先级越高）
SITE_PRIORITY = ['outdoorandcountry', 'allweathers', 'houseoffraser', 'philipmorris', 'barbour']

# 折扣规则：按顺序匹配，命中即应用（先到先得）
# 说明：
#   - site: str 或 [str, ...]，匹配站点名（完全相等）
#   - prefix: tuple/list/set，商品编码前缀（color_code 开头）
#   - regex: 可选，完整正则匹配 color_code（优先级比 prefix 高，如果两者同时给，满足任一即可）
#   - percent: 折扣系数，例如 0.9 表示 9 折；不写则视为 1.0（不打折）
#   - minus:   直接减价（GBP），默认 0
#   - floor:   折后向下取整到多少小数位（例如 2 表示保留 2 位小数），缺省为 2
DISCOUNT_RULES = [
    {"site": "allweathers", "prefix": ("MWX0018","MWX0010","MWX0017","MWX0339","LWX0667","LWX0668"), "percent": 0.75},
    {"site": "allweathers", "percent": 0.90},
    {"site": "outdoorandcountry", "percent": 0.95},
]

# ============ 工具函数 ============
def _site_rank_case_sql(alias: str = "tpo") -> str:
    """构造站点优先级 CASE WHEN SQL 片段"""
    if not SITE_PRIORITY:
        return "CASE WHEN 1=1 THEN 999 END"
    parts = []
    for i, name in enumerate(SITE_PRIORITY):
        safe = name.replace("'", "''")
        parts.append(f"WHEN {alias}.site_name = '{safe}' THEN {i}")
    parts.append("ELSE 999")
    return "CASE " + " ".join(parts) + " END"

def _normalize_sites_field(site_field: Any) -> List[str]:
    if site_field is None:
        return []
    vals = (list(site_field) if isinstance(site_field, (list,tuple,set)) else [site_field])
    canon = [canonical_site(str(s)) for s in vals]
    return [s for s in canon if s]

def _match_rule(site: str, code: str, rule: Dict[str, Any]) -> bool:
    """判断单条规则是否命中"""
    site = canonical_site(site or "") or ""  # ← 把 offers 里的站点也标准化
    sites = _normalize_sites_field(rule.get("site"))
    if sites and site not in sites:
        return False
    # 若提供 regex，命中即返回 True
    regex = rule.get("regex")
    if regex and re.search(regex, code):
        return True
    # 否则看前缀
    prefixes = rule.get("prefix") or ()
    if prefixes:
        return any(code.startswith(p) for p in prefixes)
    # 仅站点规则也可生效
    return bool(sites)

def _apply_discount_by_rules(site: str, code: str, base_price: Optional[float]) -> Optional[float]:
    """按 DISCOUNT_RULES 计算折扣价；无匹配或 base_price 为空则返回 base_price 原值"""
    if base_price is None:
        return None
    price = float(base_price)
    for rule in DISCOUNT_RULES:
        if _match_rule(site, code, rule):
            percent = float(rule.get("percent", 1.0))
            minus = float(rule.get("minus", 0.0))
            floor_digits = int(rule.get("floor", 2))
            price = price * percent - minus
            # 负保护
            if price < 0:
                price = 0.0
            # 统一四舍五入到 floor 指定位数
            price = round(price, floor_digits)
            break  # 命中第一条规则后即停止
    return price

# ============ 主流程 ============
def backfill_barbour_inventory():
    dsn = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]
    conn = psycopg2.connect(**dsn)
    with conn:
        with conn.cursor() as cur:
            # 1) 拉取三张表
            cur.execute("SELECT id, product_code, size FROM barbour_inventory;")
            inv_rows = cur.fetchall()

            cur.execute("""
                SELECT id, color_code, size, title, product_description, gender, category
                FROM barbour_products;
            """)
            prod_rows = cur.fetchall()

            cur.execute("""
                SELECT id, color_code, size, site_name, offer_url, price_gbp,
                       stock_status, can_order, last_checked
                FROM offers;
            """)
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
            # 新增 discount_price_gbp 字段（在临时表中预先计算好）
            cur.execute("""
                CREATE TEMP TABLE tmp_o (
                  o_id INT PRIMARY KEY,
                  color_code VARCHAR(50),
                  size_norm VARCHAR(32),
                  site_name VARCHAR(100),
                  offer_url TEXT,
                  price_gbp NUMERIC(10,2),
                  discount_price_gbp NUMERIC(10,2),
                  stock_status VARCHAR(50),
                  can_order BOOLEAN,
                  last_checked TIMESTAMP
                ) ON COMMIT DROP;
            """)

            inv_payload = [(i, code, clean_size_for_barbour(sz)) for (i, code, sz) in inv_rows]
            execute_values(
                cur,
                "INSERT INTO tmp_bi (bi_id, product_code, size_norm) VALUES %s",
                inv_payload, page_size=1000
            )

            prod_payload = [
                (i, code, clean_size_for_barbour(sz), title, desc, gd, cat)
                for (i, code, sz, title, desc, gd, cat) in prod_rows
            ]
            execute_values(
                cur,
                "INSERT INTO tmp_p (p_id, color_code, size_norm, title, product_description, gender, category) VALUES %s",
                prod_payload, page_size=1000
            )

            offer_payload = []
            for (i, code, sz, site, url, price, stock, can, ts) in offer_rows:
                # 位置：for (i, code, sz, site, url, price, stock, can, ts) in offer_rows: 这一段
                norm_size = clean_size_for_barbour(sz)
                site = canonical_site(site) or site      # ← 加这一行（只改名，不动逻辑）
                disc_price = _apply_discount_by_rules(site or "", code or "", float(price) if price is not None else None)
                offer_payload.append((i, code, norm_size, site, url, price, disc_price, stock, can, ts))
            execute_values(
                cur,
                "INSERT INTO tmp_o (o_id, color_code, size_norm, site_name, offer_url, price_gbp, discount_price_gbp, stock_status, can_order, last_checked) VALUES %s",
                offer_payload, page_size=1000
            )

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

            # 4) Step 2A：可下单有货择优（使用折扣后价格字段）
            site_rank_case = _site_rank_case_sql("tpo")
            cur.execute(f"""
                WITH avail AS (
                SELECT
                    tpo.color_code,
                    tpo.size_norm,
                    tpo.site_name,
                    tpo.offer_url,
                    tpo.price_gbp,
                    tpo.discount_price_gbp,
                    COALESCE(tpo.discount_price_gbp, tpo.price_gbp) AS eff_price,
                    /* 站点优先级 */
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
                    color_code, size_norm, site_name, offer_url, price_gbp, discount_price_gbp, eff_price
                FROM avail
                /* ✅ 先比折后价 eff_price，平手再看站点优先级，最后看时间新鲜度 */
                ORDER BY color_code, size_norm,
                         eff_price ASC NULLS LAST,
                         site_rank ASC,
                         last_checked DESC
            )
            UPDATE barbour_inventory AS bi
            SET
                source_site         = b.site_name,
                source_offer_url    = b.offer_url,
                source_price_gbp    = b.price_gbp,
                discount_price_gbp  = b.discount_price_gbp,
                stock_count         = %s,
                last_checked        = NOW()
            FROM tmp_bi tbi
            JOIN best_avail b
              ON b.color_code = tbi.product_code
             AND b.size_norm  = tbi.size_norm
            WHERE bi.id = tbi.bi_id
              AND tbi.size_norm <> 'Unknown';
            """, (STOCK_WHEN_AVAILABLE,))
            print(f"Step2A 可下单有货选源（含折扣）：更新 {cur.rowcount} 行")

            # 5) Step 2B：任意报价兜底（使用折扣后价格字段）
            cur.execute(f"""
                WITH any_offer AS (
                    SELECT
                        tpo.color_code,
                        tpo.size_norm,
                        tpo.site_name,
                        tpo.offer_url,
                        tpo.price_gbp,
                        tpo.discount_price_gbp,
                        COALESCE(tpo.discount_price_gbp, tpo.price_gbp) AS eff_price,
                        {site_rank_case} AS site_rank,
                        tpo.last_checked
                    FROM tmp_o tpo
                ),
                best_any AS (
                    SELECT DISTINCT ON (color_code, size_norm)
                        color_code, size_norm, site_name, offer_url, price_gbp, discount_price_gbp, eff_price
                    FROM any_offer
                    /* ✅ 同样先比折后价，再看站点优先级 */
                    ORDER BY color_code, size_norm,
                             eff_price ASC NULLS LAST,
                             site_rank ASC,
                             last_checked DESC
                )
                UPDATE barbour_inventory AS bi
                SET
                    source_site         = b.site_name,
                    source_offer_url    = b.offer_url,
                    source_price_gbp    = b.price_gbp,
                    discount_price_gbp  = b.discount_price_gbp,
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
            print(f"Step2B 不可下单兜底选源（含折扣）：更新 {cur.rowcount} 行")

    print("✅ 回填完成（已加入按站点/编码前缀/正则的折扣价逻辑，尺码已归一化对齐）。")

if __name__ == "__main__":
    backfill_barbour_inventory()
