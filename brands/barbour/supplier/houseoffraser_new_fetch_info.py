# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour - 新版 Next.js PDP 解析
- 不再尝试旧版；统一按新栈(JSON-LD + DOM)解析
- v2 版在保持业务逻辑/输出不变的前提下，改成多线程 + 每线程一个 driver。
- 输出沿用旧有 KV 文本模板，不改字段名/顺序，保证下游兼容
"""

from __future__ import annotations

import os, time, tempfile, threading, html as ihtml
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- 依赖 ----
import re
import json
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

# ---- 项目内模块（保持不变）----
from config import BARBOUR, BRAND_CONFIG
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from brands.barbour.core.sim_matcher import match_product, choose_best
from common_taobao.core.size_utils import clean_size_for_barbour as _norm_size  # 尺码清洗
from common_taobao.core.driver_auto import build_uc_driver  # 目前没用，但保留以兼容原代码
from config import BARBOUR, BRAND_CONFIG, SETTINGS
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# ================== 常量/路径 ==================
SITE_NAME = canon("houseoffraser")
LINKS_FILE: str = BARBOUR["LINKS_FILES"]["houseoffraser"]

TXT_DIR: Path = Path(BARBOUR["TXT_DIRS"]["houseoffraser"])
TXT_DIR.mkdir(parents=True, exist_ok=True)

DEBUG_DIR: Path = TXT_DIR / "_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS_TABLE: str = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE: Optional[str] = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

WAIT_HYDRATE_SECONDS = 22
DEFAULT_DELAY = 0.0
MAX_WORKERS_DEFAULT = 1  # 默认串行；并发请传入 max_workers > 1
MIN_SCORE = 0.72
MIN_LEAD = 0.04
NAME_WEIGHT = 0.75
COLOR_WEIGHT = 0.25

# ================== URL→Code 缓存 ==================
URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False

# ================== 尺码相关常量 ==================
WOMEN_ORDER = ["4", "6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA_ORDER = ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

# ================== 尺码工具函数（保持你原来逻辑） ==================
def _normalize_size_token_for_barbour(raw_token: str, gender: str) -> str | None:
    """
    把站点尺寸（可能是 '12(M)' / '16 (XL)' / 'UK 14' / 'XL' / '32'）清洗成标准内部码：
      - 女款: 数字 4,6,8,10,12,14,16,18,20
      - 男款上衣: 2XS,XS,S,M,L,XL,2XL,3XL
      - 男款下装: 30,32,34,...,50 (偶数)
    如果不是合法尺码，返回 None。
    """

    if not raw_token:
        return None

    s = raw_token.strip().upper()

    # 去掉括号部分，比如 "12(M)" -> "12"
    s = re.sub(r"\(.*?\)", "", s)
    s = s.strip()

    # 去掉 "UK 12" / "UK12" / "EU 40" 这种前缀
    s = re.sub(r"^(UK|EU|US)\s*", "", s)

    # 压紧空格、连字符
    s = re.sub(r"\s+", "", s)
    s = s.replace("-", "")

    # --- 女款逻辑 ---
    # 注意：不用再只看中文“女”，而是用 _is_female_gender()
    if _is_female_gender(gender):
        m = re.match(r"^(\d{1,2})$", s)
        if m:
            n = int(m.group(1))
            if n in {4, 6, 8, 10, 12, 14, 16, 18, 20}:
                return str(n)
        # 女装不输出 S/M/L 之类，直接丢弃
        return None

    # --- 男款逻辑 ---
    # 数字裤装尺码，比如 32, 34, 36...（腰围）
    m = re.match(r"^(\d{2})$", s)
    if m:
        n = int(m.group(1))
        if 30 <= n <= 50 and n % 2 == 0:
            return str(n)

    # 上装字母码，比如 XL, XXL, 3XL...
    mapped = ALPHA_MAP.get(s)
    if mapped:
        return mapped

    return None


def _is_female_gender(g: str) -> bool:
    """
    判断是不是女款:
    - 包含中文"女"
    - 或英文 women / womens / girl / girls / ladies / female
    """
    if not g:
        return False
    gl = g.strip().lower()
    if "女" in gl:
        return True
    female_keys = ["women", "womens", "woman", "girl", "girls", "ladies", "lady", "female"]
    return any(k in gl for k in female_keys)


def _is_male_gender(g: str) -> bool:
    """
    判断是不是男款:
    - 包含中文"男"
    - 或英文 men / mens / boy / boys / male
    """
    if not g:
        return False
    gl = g.strip().lower()
    if "男" in gl:
        return True
    male_keys = ["men", "mens", "man", "boy", "boys", "male"]
    return any(k in gl for k in male_keys)


def _choose_size_family_for_gender(gender: str, observed_sizes: set[str]) -> list[str]:
    """
    决定输出哪套完整尺码序列。
    - 女款：固定女装数字码 ["4","6","8","10","12","14","16","18","20"]
    - 男款：在男装字母系(2XS..3XL) 和 男装数字腰围系(30..50 偶数)里二选一
      （谁出现得多就用谁），然后我们会在后面补全没出现的码。
    """
    if _is_female_gender(gender):
        return WOMEN_ORDER[:]

    # 男款 / 未知 默认按男逻辑
    has_num = any(k in MEN_NUM_ORDER for k in observed_sizes)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in observed_sizes)

    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]

    if has_num or has_alpha:
        num_count = sum(1 for k in observed_sizes if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in observed_sizes if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]

    # 实在看不出来，兜底用男款字母系
    return MEN_ALPHA_ORDER[:]


def _finalize_sizes_for_hof(raw_size_dict: Dict[str, Dict[str, int]], gender: str) -> Tuple[str, str]:
    """
    raw_size_dict 形如:
        { "12(M)": {"stock":3}, "14(L)": {"stock":3}, "16(XL)": {"stock":3} }

    gender: 现在可能是 "women"/"men"/"No Data"/"男款"/"女款" 等等

    输出:
      Product Size:        "10:无货;12:有货;14:有货;16:有货;18:无货;20:无货"
      Product Size Detail: "10:0:000...;12:3:000...;14:3:000...;16:3:000...;18:0:000...;20:0:000..."
    """

    # 1. 清洗成我们标准码，并记录库存
    normalized_stock: Dict[str, int] = {}
    for raw_label, meta in (raw_size_dict or {}).items():
        norm = _normalize_size_token_for_barbour(raw_label, gender or "")
        if not norm:
            continue
        stock_qty = int(meta.get("stock", 0))
        if norm not in normalized_stock:
            normalized_stock[norm] = stock_qty
        else:
            # 如果之前是无货，现在发现有货，就更新
            if normalized_stock[norm] == 0 and stock_qty > 0:
                normalized_stock[norm] = stock_qty

    # 2. 选定应该用哪一套完整尺码表
    observed = set(normalized_stock.keys())
    full_order = _choose_size_family_for_gender(gender or "", observed)

    # 3. 把不在该体系里的码剔除
    for k in list(normalized_stock.keys()):
        if k not in full_order:
            normalized_stock.pop(k, None)

    # 4. 按 full_order 补全所有码：有的写真实库存>0 => 有货，否则无货
    EAN_PLACEHOLDER = "0000000000000"
    size_line_parts = []
    size_detail_parts = []

    for size_token in full_order:
        qty = normalized_stock.get(size_token, 0)
        status = "有货" if qty > 0 else "无货"

        size_line_parts.append(f"{size_token}:{status}")
        size_detail_parts.append(f"{size_token}:{DEFAULT_STOCK_COUNT if qty > 0 else 0}:{EAN_PLACEHOLDER}")

    product_size_str = ";".join(size_line_parts) if size_line_parts else "No Data"
    product_size_detail_str = ";".join(size_detail_parts) if size_detail_parts else "No Data"

    return product_size_str, product_size_detail_str


# ================== HTML / JSON 解析辅助 ==================
def _extract_next_json_chunks(html: str) -> str:
    m = re.search(r'"gender":"(?:Mens|Womens|Girls|Boys)".{0,2000}?"variants":\[(.*?)\]\}', html, re.S)
    if m:
        return m.group(0)
    m = re.search(r'"sizes":\{"allSizes":\[(.*?)\]\}', html, re.S)
    return m.group(0) if m else ""


def _extract_color_from_og_alt(soup: BeautifulSoup) -> str:
    for tag in soup.find_all("meta", {"property": "og:image:alt"}):
        content = (tag.get("content") or "").strip()
        if content:
            first = content.split(" - ", 1)[0]  # e.g. "Black BK11"
            first = re.sub(r"\b[A-Z]{2}\d{2,}\b", "", first).strip()
            if first:
                return first
    return ""


def _extract_all_sizes(html: str):
    sizes = []
    ms = re.search(r'"sizes"\s*:\s*\{\s*"allSizes"\s*:\s*(\[[^\]]*\])', html, re.S | re.I)
    if ms:
        try:
            arr = json.loads(ms.group(1))
            seen = set()
            for it in arr:
                raw = (it.get("size") or "").strip()
                if not raw:
                    continue
                size = _norm_size(raw) or raw
                if size not in seen:
                    seen.add(size)
                    sizes.append(size)
        except Exception:
            pass
    return sizes


def _extract_sizes_dom_fallback(soup: BeautifulSoup):
    enabled = []
    disabled = []

    for btn in soup.select('[data-testid="swatch-button-enabled"]'):
        raw = (btn.get("value") or btn.get_text() or "").strip()
        if not raw:
            continue
        size = _norm_size(raw) or raw
        enabled.append(size)

    for btn in soup.select('[data-testid="swatch-button-disabled"], button[disabled][data-testid*="swatch"]'):
        raw = (btn.get("value") or btn.get_text() or "").strip()
        if not raw:
            continue
        size = _norm_size(raw) or raw
        disabled.append(size)

    if not enabled and not disabled:
        return []

    seen = set()
    entries = []
    for s in enabled:
        if s not in seen:
            seen.add(s)
            entries.append((s, "有货"))
    for s in disabled:
        if s not in seen:
            seen.add(s)
            entries.append((s, "无货"))

    return entries


def _extract_color_gender_from_json(html: str) -> (str, str):
    block = _extract_next_json_chunks(html)
    color = ""
    gender = ""
    if block:
        mc = re.search(r'"color"\s*:\s*"([^"]+)"', block)
        if mc:
            raw = mc.group(1)
            color = re.sub(r"\b[A-Z]{2}\d{2,}\b", "", raw).strip()
        mg = re.search(r'"gender"\s*:\s*"(Mens|Womens|Girls|Boys)"', block)
        if mg:
            g = mg.group(1).lower()
            mapping = {"mens": "men", "womens": "women", "girls": "women", "boys": "men"}
            gender = mapping.get(g, g)
    return color, gender


def _extract_color_new(soup: BeautifulSoup, html: str) -> str:
    color, _ = _extract_color_gender_from_json(html)
    if color:
        return color
    alt_color = _extract_color_from_og_alt(soup)
    return alt_color or "No Data"


def _infer_gender_from_code(code: Optional[str]) -> str:
    """
    仅在已拿到产品编码时启用。
    """
    if not code:
        return "No Data"
    c = code.strip().upper()
    if c.startswith("M"):
        return "men"
    if c.startswith("L"):
        return "women"
    male3 = ("MQU", "MWX", "MSH", "MKN", "MGL", "MFL", "MGI", "MLI", "MSW", "MCA")
    female3 = ("LQU", "LWX", "LSH", "LKN", "LGL", "LFL", "LGI", "LLI", "LSW", "LCA")
    pre3 = c[:3]
    if pre3 in male3:
        return "men"
    if pre3 in female3:
        return "women"
    return "No Data"


def _gender_to_cn(g: str) -> str:
    if not g:
        return "No Data"
    g = g.strip().lower()
    if g in ("men", "mens"):
        return "男款"
    if g in ("women", "womens"):
        return "女款"
    if g in ("boys", "boy"):
        return "男款"
    if g in ("girls", "girl"):
        return "女款"
    return "No Data"


def _extract_gender_new(soup: BeautifulSoup, html: str, url: str) -> str:
    """
    返回：men / women / No Data
    """
    bc = soup.select("nav[aria-label*=breadcrumb] a, ol[aria-label*=breadcrumb] a")
    bc_txt = " ".join(a.get_text(" ", strip=True) for a in bc) if bc else ""
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_desc = soup.find("meta", {"name": "description"})
    desc = (meta_desc.get("content") or "") if meta_desc else ""
    blob = " ".join([bc_txt.lower(), title.lower(), desc.lower()])

    if any(w in blob for w in ("womens", "women", "ladies", "women's", "lady")):
        return "women"
    if any(w in blob for w in ("mens", "men", "men's", "man")):
        return "men"

    ul = (url or "").lower()
    if "/women" in ul or "womens" in ul:
        return "women"
    if "/men" in ul or "mens" in ul:
        return "men"

    m = re.search(r'"gender"\s*:\s*"(Mens|Womens|Girls|Boys)"', html, re.I)
    if m:
        g = m.group(1).lower()
        mapping = {"mens": "men", "womens": "women", "girls": "women", "boys": "men"}
        return mapping.get(g, g)

    return "No Data"


def _extract_sizes_from_variants(html: str):
    entries = []
    patt = r'"size"\s*:\s*"([^"]+?)".{0,4000}?"isOnStock"\s*:\s*(true|false)'
    for m in re.finditer(patt, html, re.S | re.I):
        raw = m.group(1).strip()
        size = _norm_size(raw) or raw
        avail = (m.group(2).lower() == "true")
        if size:
            entries.append((size, "有货" if avail else "无货"))
    return entries


def _extract_sizes_from_allSizes(html: str):
    entries = []
    ms = re.search(r'"sizes"\s*:\s*\{\s*"allSizes"\s*:\s*(\[[^\]]*\])', html, re.S)
    if ms:
        try:
            arr = json.loads(ms.group(1))
            for it in arr:
                size = (it.get("size") or "").strip()
                if size:
                    entries.append((size, "有货"))
        except Exception:
            pass
    return entries


def _extract_sizes_new(soup: BeautifulSoup) -> Dict[str, Dict[str, int]]:
    """
    抓页面上的尺码按钮，返回:
    {
        "12(M)": {"stock": 3},
        ...
    }
    """
    results: Dict[str, Dict[str, int]] = {}

    for btn in soup.select("button[data-testid='swatch-button-enabled'], button[data-testid='swatch-button-disabled']"):
        label = (btn.get("value") or btn.get_text() or "").strip()
        if not label:
            continue
        data_tid = btn.get("data-testid", "")
        in_stock = "enabled" in data_tid
        stock_qty = DEFAULT_STOCK_COUNT if in_stock else 0
        if label not in results:
            results[label] = {"stock": stock_qty}
        else:
            if results[label]["stock"] == 0 and stock_qty > 0:
                results[label]["stock"] = stock_qty

    return results


def _normalize_url(u: str) -> str:
    return u.strip() if u else ""


def get_dbapi_connection(conn_or_engine):
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
    global URL_CODE_CACHE, _URL_CODE_CACHE_READY
    if _URL_CODE_CACHE_READY:
        return URL_CODE_CACHE

    cache = OrderedDict()

    if offers_table:
        candidates = [
            ("offer_url", "product_code"),
            ("source_url", "product_code"),
            ("product_url", "product_code"),
            ("offer_url", "color_code"),
            ("source_url", "color_code"),
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


def _atomic_write_bytes(data: bytes, dst: Path, retries: int = 6, backoff: float = 0.25) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=str(dst.parent),
                prefix=".tmp_",
                suffix=f".{os.getpid()}.{threading.get_ident()}",
            ) as tf:
                tmp = Path(tf.name)
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())
            try:
                os.replace(tmp, dst)
            finally:
                if tmp and tmp.exists():
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
            return True
        except Exception:
            if dst.exists():
                return True
            time.sleep(backoff * (i + 1))
            try:
                if tmp and tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass
    return dst.exists()


def _kv_txt_bytes(info: Dict[str, Any]) -> bytes:
    fields = [
        "Product Code",
        "Product Name",
        "Product Description",
        "Product Gender",
        "Product Color",
        "Product Price",
        "Adjusted Price",
        "Product Material",
        "Style Category",
        "Feature",
        "Product Size",
        "Product Size Detail",
        "Source URL",
        "Site Name",
    ]
    lines = [f"{k}: {info.get(k, 'No Data')}" for k in fields]
    return ("\n".join(lines) + "\n").encode("utf-8", errors="ignore")


def _safe_name(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|'\s]+", "_", (s or "NoName"))


def _dump_debug_html(html: str, url: str, tag: str = "debug1") -> Path:
    short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
    out = DEBUG_DIR / f"{tag}_{short}.html"
    _atomic_write_bytes(html.encode("utf-8", errors="ignore"), out)
    print(f"🧪 HTML dump → {out}")
    return out


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _to_num(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s.replace(",", ""))
    return float(m.group(1)) if m else None


def _soft_scroll(driver, steps=6, pause=0.45):
    for _ in range(steps):
        try:
            driver.execute_script("window.scrollBy(0, Math.floor(document.body.scrollHeight * 0.28));")
        except Exception:
            pass
        time.sleep(pause)
    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass
    time.sleep(0.3)


def wait_pdp_ready(driver, timeout: int = WAIT_HYDRATE_SECONDS) -> bool:
    key_css = ", ".join(
        [
            "[data-testid*='price']",
            "[data-component*='price']",
            "[itemprop='price']",
            "meta[itemprop='price']",
            "h1",
            "[data-testid*='title']",
            "[data-component*='title']",
            "button[aria-pressed][data-testid*='size']",
            "li[role='option']",
            "div[role='option']",
            "option[data-testid*='drop-down-option']",
            "#sizeDdl option",
            "script[type='application/ld+json']",
        ]
    )
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.find_elements(By.CSS_SELECTOR, key_css):
                return True
        except Exception:
            pass
        _soft_scroll(driver, steps=2, pause=0.45)
    return False


def _pick_first(x):
    if isinstance(x, list) and x:
        return x[0]
    return x


def parse_jsonld(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        txt = (tag.string or tag.text or "").strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
            blocks.append(data)
        except Exception:
            continue

    def _walk(obj):
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from _walk(v)
        elif isinstance(obj, list):
            for it in obj:
                yield from _walk(it)

    product = None
    offers = []
    for b in blocks:
        for node in _walk(b):
            if not isinstance(node, dict):
                continue
            t = node.get("@type") or node.get("@type".lower())
            if t == "Product":
                product = node
            elif t == "Offer":
                offers.append(node)

    out = {}
    if product:
        out["title"] = _pick_first(product.get("name"))
        out["sku"] = product.get("sku") or product.get("mpn") or product.get("productID")
        brand = product.get("brand")
        if isinstance(brand, dict):
            out["brand"] = brand.get("name")
        else:
            out["brand"] = brand
        imgs = product.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        out["images"] = imgs
        desc = product.get("description") or ""
        desc = re.sub(r"<[^>]+>", " ", desc)
        out["description"] = re.sub(r"\s+", " ", ihtml.unescape(desc)).strip()

    price = currency = availability = None
    url = None
    for off in offers:
        p = off.get("price") or off.get("priceSpecification", {}).get("price")
        if p:
            price = p
            currency = off.get("priceCurrency") or off.get("priceSpecification", {}).get("priceCurrency")
            availability = off.get("availability")
            url = off.get("url")
            break
    if price:
        out["price"] = str(price)
    if currency:
        out["currency"] = currency
    if availability:
        out["availability"] = availability.split("/")[-1] if "/" in availability else availability
    if url:
        out["url"] = url
    return out


GENDER_WORDS = (
    ("Womens", ("womens", "women", "ladies", "women's", "lady")),
    ("Mens", ("mens", "men", "men's", "man")),
    ("Boys", ("boys", "boy")),
    ("Girls", ("girls", "girl")),
)
COLOR_WORDS = [
    "Black",
    "Navy",
    "Green",
    "Olive",
    "Brown",
    "Blue",
    "Red",
    "Cream",
    "Beige",
    "Grey",
    "Gray",
    "White",
    "Pink",
    "Burgundy",
    "Khaki",
    "Stone",
    "Tan",
    "Orange",
    "Yellow",
    "Purple",
]


def _infer_gender_from_text(*texts) -> str:
    blob = " ".join(t.lower() for t in texts if t).strip()
    for label, keys in GENDER_WORDS:
        if any(k in blob for k in keys):
            return label
    return "No Data"


def _extract_gender(html: str, soup: BeautifulSoup, title: str, desc: str, url: str) -> str:
    bc = soup.select("nav[aria-label*=breadcrumb] a, ol[aria-label*=breadcrumb] a")
    bc_txt = " ".join(a.get_text(" ", strip=True) for a in bc) if bc else ""
    g = _infer_gender_from_text(bc_txt, title, desc, url)
    if g != "No Data":
        return g
    m = re.search(r'"gender"\s*:\s*"(?P<g>Womens|Mens|Boys|Girls)"', html, re.I)
    if m:
        return m.group("g").capitalize()
    return _infer_gender_from_text(desc, title)


def _extract_color(html: str, soup: BeautifulSoup, title: str) -> str:
    el = soup.select_one(
        "[data-testid*='colour'] [data-testid*='value'], "
        "[data-component*='colour'], "
        "[aria-label*='Colour'] [aria-live]"
    )
    if el:
        c = el.get_text(strip=True)
        if c:
            return c
    m = re.search(r'"color"\s*:\s*"([A-Za-z /-]{3,20})"', html)
    if m:
        return m.group(1).strip()
    for w in COLOR_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", title, re.I):
            return w
    return "No Data"


def _extract_sizes_legacy_dropdown(soup: BeautifulSoup) -> Tuple[str, str]:
    entries = []

    for btn in soup.select("button[aria-pressed][data-testid*='size'], button[aria-pressed][aria-label*='Size']"):
        lab = (btn.get_text() or btn.get("aria-label") or "").strip()
        if not lab:
            continue
        disabled = (btn.get("disabled") is not None) or (btn.get("aria-disabled") in ("true", "True"))
        status = "无货" if disabled else "有货"
        entries.append((lab, status))

    for node in soup.select("li[role='option'], div[role='option']"):
        lab = (node.get_text() or node.get("aria-label") or "").strip()
        if not lab:
            continue
        if lab.lower().startswith(("select size", "choose size")):
            continue
        disabled = node.get("aria-disabled") in ("true", "True") or "disabled" in (node.get("class") or [])
        status = "无货" if disabled else "有货"
        entries.append((lab, status))

    for opt in soup.select("select option[data-testid*='drop-down-option'], #sizeDdl option"):
        lab = (opt.get_text() or "").strip()
        if not lab or lab.lower().startswith(("select", "choose")):
            continue
        clean = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", lab, flags=re.I).strip(" -/")
        disabled = opt.has_attr("disabled") or (opt.get("aria-disabled") == "true") or "out of stock" in lab.lower()
        status = "无货" if disabled else "有货"
        entries.append((clean or lab, status))

    if not entries:
        return "No Data", "No Data"

    ordered = []
    seen = {}
    for label, status in entries:
        label = re.sub(r"\s+", " ", label).strip()
        if label not in seen or (seen[label] == "无货" and status == "有货"):
            seen[label] = status
            if label not in ordered:
                ordered.append(label)

    EAN = "0000000000000"
    product_size = ";".join(f"{s}:{seen[s]}" for s in ordered) or "No Data"
    product_size_detail = ";".join(
        f"{s}:{DEFAULT_STOCK_COUNT if seen[s]=='有货' else 0}:{EAN}" for s in ordered
    ) or "No Data"
    return product_size, product_size_detail


def _from_jsonld_product_new(soup: BeautifulSoup) -> Dict[str, Any]:
    out = {"name": None, "description": None, "sku": None}
    try:
        html = str(soup)
        jd = parse_jsonld(html) or {}
    except Exception:
        jd = {}

    title = jd.get("title")
    if title:
        out["name"] = title
    if jd.get("description"):
        out["description"] = jd["description"]
    if jd.get("sku"):
        out["sku"] = jd["sku"]

    if not out["name"]:
        h1 = soup.select_one("h1,[data-testid*='title'],[data-component*='title']")
        out["name"] = h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else None)

    return out


def _parse_price_string(txt: str) -> float | None:
    if not txt:
        return None
    cleaned = txt.strip()

    m_symbol = re.search(r"£\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_symbol:
        return float(m_symbol.group(1))

    m_pence = re.search(r"^([0-9]{3,})$", cleaned)
    if m_pence:
        try:
            pence_val = int(m_pence.group(1))
            return round(pence_val / 100.0, 2)
        except Exception:
            pass

    m_plain = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_plain:
        return float(m_plain.group(1))

    return None


def _extract_prices_new(soup: BeautifulSoup) -> tuple[str, str]:
    price_block = soup.select_one('p[data-testid="price"]')
    if not price_block:
        return ("No Data", "No Data")

    discounted_span = price_block.select_one("span[class*='Price_isDiscounted']")
    discounted_price = None
    if discounted_span:
        discounted_price = _parse_price_string(discounted_span.get_text(strip=True))

    ticket_span = price_block.select_one('span[data-testid="ticket-price"]')
    ticket_price = None
    if ticket_span:
        ticket_price = _parse_price_string(ticket_span.get_text(strip=True))

    if ticket_price is None:
        block_testvalue = price_block.get("data-testvalue")
        ticket_price = _parse_price_string(block_testvalue)

    if ticket_price is None:
        first_span = price_block.find("span")
        if first_span:
            ticket_price = _parse_price_string(first_span.get_text(strip=True))

    if discounted_price is not None and ticket_price is not None:
        product_price_val = ticket_price
        adjusted_price_val = discounted_price
    else:
        product_price_val = ticket_price or discounted_price
        adjusted_price_val = None

    product_price_str = f"{product_price_val:.2f}" if product_price_val is not None else "No Data"
    adjusted_price_str = f"{adjusted_price_val:.2f}" if adjusted_price_val is not None else "No Data"

    return product_price_str, adjusted_price_str


def _decide_gender_for_logic(sku: str, soup: BeautifulSoup, html: str, url: str) -> str:
    sku_guess = _infer_gender_from_code(sku or "")
    if sku_guess and sku_guess != "No Data":
        return sku_guess

    page_guess = _extract_gender_new(soup, html, url)
    if page_guess and page_guess != "No Data":
        return page_guess

    return "No Data"


def parse_info_new(html: str, url: str, conn) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    jd = _from_jsonld_product_new(soup) or {}
    title_guess = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc_guess = jd.get("description") or "No Data"
    sku_guess = jd.get("sku") or "No Data"

    color_guess = _extract_color_new(soup, html) or "No Data"
    raw_sizes = _extract_sizes_new(soup)
    product_price_str, adjusted_price_str = _extract_prices_new(soup)

    norm_url = _normalize_url(url)
    final_code = URL_CODE_CACHE.get(norm_url)

    if not final_code:
        raw_conn = get_dbapi_connection(conn)
        results = match_product(
            raw_conn,
            scraped_title=title_guess or "",
            scraped_color=color_guess or "",
            table=PRODUCTS_TABLE,
            name_weight=NAME_WEIGHT,
            color_weight=COLOR_WEIGHT,
            type_weight=(1.0 - NAME_WEIGHT - COLOR_WEIGHT),
            topk=5,
            recall_limit=2000,
            min_name=0.92,
            min_color=0.85,
            require_color_exact=False,
            require_type=False,
        )
        chosen = choose_best(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
        if chosen:
            final_code = chosen

    if not final_code:
        final_code = sku_guess if sku_guess and sku_guess != "No Data" else "No Data"

    gender_for_logic = _decide_gender_for_logic(final_code, soup, html, url)
    product_size_str, product_size_detail_str = _finalize_sizes_for_hof(raw_sizes, gender_for_logic)

    def _gender_to_display(g: str) -> str:
        if g == "women":
            return "女款"
        if g == "men":
            return "男款"
        if g == "kids":
            return "童款"
        if g == "unisex":
            return "中性款"
        return "No Data"

    gender_display = _gender_to_display(gender_for_logic)

    info = {
        "Product Code": final_code or "No Data",
        "Product Name": title_guess or "No Data",
        "Product Description": desc_guess or "No Data",
        "Product Gender": gender_display or "No Data",
        "Product Color": color_guess or "No Data",
        "Product Price": product_price_str,
        "Adjusted Price": adjusted_price_str,
        "Product Material": "No Data",
        "Style Category": "casual wear",
        "Feature": "No Data",
        "Product Size": product_size_str,
        "Product Size Detail": product_size_detail_str,
        "Source URL": url,
        "Site Name": SITE_NAME,
    }

    return info


# ================== Selenium 基础（v2：多线程友好版） ==================
_thread_local_driver = threading.local()
_all_drivers = set()
_drivers_lock = threading.Lock()


def create_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=en-GB")
    options.add_argument("accept-language=en-GB,en-US;q=0.9,en;q=0.8")

    driver = uc.Chrome(
        options=options,
        version_main=142,  # ← 请根据你本地 Chrome 主版本调整
        browser_executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    with _drivers_lock:
        _all_drivers.add(driver)
    return driver


def get_driver(headless: bool = False):
    d = getattr(_thread_local_driver, "driver", None)
    if d is None:
        d = create_driver(headless=headless)
        _thread_local_driver.driver = d
    return d


def shutdown_all_drivers():
    with _drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except Exception:
                pass
        _all_drivers.clear()


def fetch_product_info_with_single_driver(driver, url: str) -> Dict[str, Any]:
    driver.get(url)
    ok = wait_pdp_ready(driver, timeout=WAIT_HYDRATE_SECONDS)
    if not ok:
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="timeout_debug")
        return parse_info_new(html, url, conn=None)
    _soft_scroll(driver, steps=6, pause=0.4)
    html = driver.page_source or ""
    _dump_debug_html(html, url, tag="debug_new")
    return parse_info_new(html, url, conn=None)


# ================== 处理单个 URL ==================
def process_url_with_driver(driver, url: str, conn: Connection, delay: float = DEFAULT_DELAY) -> Path | None:
    """
    打开单个 URL，解析出 info（已经包含最终 Product Code / Gender / 尺码等），
    然后写入 TXT。
    """
    print(f"\n🌐 正在抓取: {url}")

    driver.get(url)
    ok = wait_pdp_ready(driver, timeout=WAIT_HYDRATE_SECONDS)
    if not ok:
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="timeout_debug")
    else:
        _soft_scroll(driver, steps=6, pause=0.4)
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="debug_new")

    info = parse_info_new(html, url, conn)

    code_for_filename = info.get("Product Code") or "NoDataCode"
    code_for_filename = code_for_filename.strip() or "NoDataCode"
    safe_code_for_filename = _safe_name(code_for_filename)

    if safe_code_for_filename in ("NoDataCode", "No_Data", "NoData", "No", ""):
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        safe_name_part = _safe_name(info.get("Product Name") or "BARBOUR")
        out_path = TXT_DIR / f"{safe_name_part}_{short}.txt"
    else:
        out_path = TXT_DIR / f"{safe_code_for_filename}.txt"

    payload = _kv_txt_bytes(info)
    ok_write = _atomic_write_bytes(payload, out_path)

    if ok_write:
        print(f"✅ 写入: {out_path} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")

    if delay > 0:
        time.sleep(delay)

    return out_path


# ================== 主入口：多线程版本 ==================
def houseoffraser_fetch_info(
    max_workers: int = MAX_WORKERS_DEFAULT, delay: float = DEFAULT_DELAY, headless: bool = False
):
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return

    raw_urls = [
        line.strip()
        for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    seen = set()
    urls: list[str] = []
    for u in raw_urls:
        nu = _normalize_url(u)
        if nu in seen:
            continue
        seen.add(nu)
        urls.append(u)

    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0:
        return

    engine_url = (
        f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['dbname']}"
    )
    engine = create_engine(engine_url)

    with engine.begin() as conn:
        raw = get_dbapi_connection(conn)
        build_url_code_cache(raw, PRODUCTS_TABLE, OFFERS_TABLE, SITE_NAME)

    ok, fail = 0, 0

    try:
        first_processed = False
        if urls:
            driver = get_driver(headless=headless)
            first_url = urls[0]
            print("🕒 将打开首个商品页。请在 10 秒内手动点击 Cookie 的 'Allow all' 按钮...")
            driver.get(first_url)
            time.sleep(10)
            print("✅ 已等待 10 秒，开始正式抓取（首个商品仍然串行处理）")

            print(f"[启动] [1/{total}] {first_url}")
            with engine.begin() as conn:
                try:
                    path = process_url_with_driver(driver, first_url, conn=conn, delay=delay)
                    if path:
                        ok += 1
                    print(f"[完成] [1/{total}] {first_url} -> {path}")
                except Exception as e:
                    fail += 1
                    print(f"[失败] [1/{total}] ❌ {first_url}\n    {repr(e)}")
            first_processed = True

        remaining_urls = urls[1:] if first_processed else urls
        if not remaining_urls:
            print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")
            return

        def worker(u: str, idx: int):
            local_driver = get_driver(headless=headless)
            with engine.begin() as conn:
                path = process_url_with_driver(local_driver, u, conn=conn, delay=delay)
            return idx, u, path

        start_idx = 2 if first_processed else 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_meta = {}
            for offset, u in enumerate(remaining_urls, start=start_idx):
                idx = offset
                print(f"[启动] [{idx}/{total}] {u}")
                fut = executor.submit(worker, u, idx)
                future_to_meta[fut] = (u, idx)

            for fut in as_completed(future_to_meta):
                u, idx = future_to_meta[fut]
                try:
                    idx_ret, u_ret, path = fut.result()
                    if path:
                        ok += 1
                    else:
                        fail += 1
                    print(f"[完成] [{idx_ret}/{total}] {u_ret} -> {path}")
                except Exception as e:
                    fail += 1
                    print(f"[失败] [{idx}/{total}] ❌ {u}\n    {repr(e)}")

        print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")

    finally:
        shutdown_all_drivers()


if __name__ == "__main__":
    # 先可以用 max_workers=1 跑一遍确认行为和 v1 完全一致
    # 然后再改成 4 / 6 做并发测试
    houseoffraser_fetch_info(max_workers=4, headless=False)
