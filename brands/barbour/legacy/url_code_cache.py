# brands/barbour/core/url_code_cache.py

from collections import OrderedDict
from typing import Optional, Dict
from sqlalchemy.engine import Connection

URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False

def _normalize_url(u: str) -> str:
    return u.strip() if u else ""

def get_dbapi_connection(conn_or_engine):
    # ← 完整逻辑直接从你现有文件拷过去
    ...

def _safe_sql_to_cache(raw_conn, sql: str, params=None) -> Dict[str, str]:
    cache = OrderedDict()
    with raw_conn.cursor() as cur:
        cur.execute(sql, params or {})
        for url, code in cur.fetchall():
            if url and code:
                cache[_normalize_url(str(url))] = str(code).strip()
    return cache

def build_url_code_cache(
    raw_conn,
    products_table: str,
    offers_table: Optional[str],
    site_name: str,
):
    global URL_CODE_CACHE, _URL_CODE_CACHE_READY
    if _URL_CODE_CACHE_READY:
        return URL_CODE_CACHE

    cache = OrderedDict()

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
