# -*- coding: utf-8 -*-
"""
Barbour | 通用编码解析器
供 house / philipmorrisdirect / 以后其它站点共享：
  - 启动时预热 URL→Code 缓存
  - 每个商品页面解析时，统一通过 resolve_barbour_code 确定 Product Code
"""

from __future__ import annotations
from typing import Optional, Dict
from collections import OrderedDict

from sqlalchemy.engine import Connection

from brands.barbour.core.sim_matcher import match_product, choose_best
from brands.barbour.common.barbour_import_candidates import find_code_by_site_url  # 你已有的小工具

# ===== URL→Code 缓存 =====
URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False


def _normalize_url(u: str) -> str:
    return u.strip() if u else ""


def get_dbapi_connection(conn_or_engine):
    """从 SQLAlchemy Connection/Engine 提取原始 psycopg2 连接。"""
    if hasattr(conn_or_engine, "cursor"):
        return conn_or_engine
    if hasattr(conn_or_engine, "raw_connection"):
        return conn_or_engine.raw_connection()
    c = getattr(conn_or_engine, "connection", None)
    if c is not None:
        dbapi = getattr(c, "dbapi_connection", None)
        if dbapi is not None and hasattr(dbapi, "cursor"):
            return dbapi
        inner = getattr(c, "connection", None)
        if inner is not None and hasattr(inner, "cursor"):
            return inner
        if hasattr(c, "cursor"):
            return c
    return conn_or_engine


def _safe_sql_to_cache(raw_conn, sql: str, params=None) -> Dict[str, str]:
    cache = OrderedDict()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql, params or {})
            for url, code in cur.fetchall():
                if url and code:
                    cache[_normalize_url(str(url))] = str(code).strip()
    except Exception:
        try:
            raw_conn.rollback()
        except Exception:
            pass
    return cache


def build_url_code_cache(raw_conn, products_table: str, offers_table: Optional[str], site_name: str):
    """
    启动时构建一次 URL→ProductCode 映射缓存。
    - 先看 offers 表（以 site_name 区分站点）
    - 再看 barbour_products 里的 source_url/offer_url/product_url
    """
    global URL_CODE_CACHE, _URL_CODE_CACHE_READY
    if _URL_CODE_CACHE_READY:
        return URL_CODE_CACHE

    cache = OrderedDict()

    # 1) offers 表里记录过编码的
    if offers_table:
        candidates = [
            ("offer_url",   "product_code"),
            ("source_url",  "product_code"),
            ("product_url", "product_code"),
            ("offer_url",   "color_code"),
            ("source_url",  "color_code"),
            ("product_url", "color_code"),
        ]
        for url_col, code_col in candidates:
            sql = f"""
                SELECT {url_col}, {code_col}
                  FROM {offers_table}
                 WHERE site_name = %(site)s
                   AND {url_col} IS NOT NULL
                   AND {code_col} IS NOT NULL
            """
            cache.update(_safe_sql_to_cache(raw_conn, sql, {"site": site_name}))

    # 2) barbour_products 里的 URL→product_code
    for url_col in ("source_url", "offer_url", "product_url"):
        sql = f"""
            SELECT {url_col}, product_code
              FROM {products_table}
             WHERE {url_col} IS NOT NULL
               AND product_code IS NOT NULL
        """
        cache.update(_safe_sql_to_cache(raw_conn, sql))

    URL_CODE_CACHE = dict(cache)
    _URL_CODE_CACHE_READY = True
    print(f"🧠 URL→Code 缓存构建完成：{len(URL_CODE_CACHE)} 条")
    return URL_CODE_CACHE


def resolve_barbour_code(
    conn: Connection,
    *,
    site_name: str,
    url: str,
    products_table: str,
    offers_table: Optional[str],
    scraped_title: str,
    scraped_color: str,
    sku_guess: Optional[str],
    # 下面这些基本用 house 当前的默认值
    min_score: float = 0.72,
    min_lead: float = 0.04,
    name_weight: float = 0.75,
    color_weight: float = 0.25,
) -> str:
    """
    给定一个站点 + URL + 标题/颜色/sku_guess，返回最终 Product Code：

      1. 先查 barbour_products 中是否已给这个 (site,url) 做过人工映射
         （barbour_import_candidates 导入后的结果）
      2. 再用 URL→Code 缓存（offers + products）
      3. 再用 sim_matcher 在 barbour_products 里做模糊匹配
      4. 再兜底用 sku_guess
    """
    raw_conn = get_dbapi_connection(conn)
    norm_url = _normalize_url(url)

    # 0. 手动配置优先（你在 barbour_product_candidates 里填好，跑 import 之后
    #    会写进 barbour_products，并且 find_code_by_site_url 就能命中）
    manual_code = find_code_by_site_url(raw_conn, site_name, norm_url)
    if manual_code:
        return manual_code

    # 1. URL→Code 缓存（启动时已 build，一般命中率很高）
    if not _URL_CODE_CACHE_READY:
        build_url_code_cache(raw_conn, products_table, offers_table, site_name)

    final_code = URL_CODE_CACHE.get(norm_url)
    if final_code:
        return final_code

    # 2. DB 模糊匹配（标题 + 颜色）
    results = match_product(
        raw_conn,
        scraped_title=scraped_title or "",
        scraped_color=scraped_color or "",
        table=products_table,
        name_weight=name_weight,
        color_weight=color_weight,
        type_weight=(1.0 - name_weight - color_weight),
        topk=5,
        recall_limit=2000,
        min_name=0.92,
        min_color=0.85,
        require_color_exact=False,
        require_type=False,
    )
    chosen = choose_best(results, min_score=min_score, min_lead=min_lead)
    if chosen:
        return chosen

    # 3. 兜底：用 JSON-LD 里的 sku_guess
    sku_guess = (sku_guess or "").strip()
    if sku_guess and sku_guess != "No Data":
        return sku_guess

    return "No Data"
