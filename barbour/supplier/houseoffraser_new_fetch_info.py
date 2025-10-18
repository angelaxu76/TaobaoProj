# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour - 新版 Next.js PDP 解析
- 不再尝试旧版；统一按新栈(JSON-LD + DOM)解析
- 单实例 Selenium（undetected-chromedriver），首个商品页等待10秒手动点 Cookie
- 输出沿用旧有 KV 文本模板，不改字段名/顺序，保证下游兼容
"""

from __future__ import annotations

from logging import info
import os, re, json, time, tempfile, threading, html as ihtml
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import urlparse, parse_qsl, urlunparse, urlencode
from collections import OrderedDict

# ---- 依赖 ----
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

# ---- 项目内模块（保持不变）----
from config import BARBOUR, BRAND_CONFIG
from barbour.core.site_utils import assert_site_or_raise as canon
from barbour.core.sim_matcher import match_product, choose_best, explain_results
from common_taobao.size_utils import clean_size_for_barbour as _norm_size  # 尺码清洗

# ================== 常量/路径 ==================
SITE_NAME = canon("houseoffraser")
LINKS_FILE: str = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR: Path = TXT_DIR / "_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS_TABLE: str = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE: Optional[str] = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

WAIT_HYDRATE_SECONDS = 22
DEFAULT_DELAY = 0.0
MAX_WORKERS_DEFAULT = 1  # 建议串行最稳；并发请改为“每线程1个driver”方案
MIN_SCORE = 0.72
MIN_LEAD = 0.04
NAME_WEIGHT = 0.75
COLOR_WEIGHT = 0.25

# ================== URL→Code 缓存 ==================
URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False


import json, re
from bs4 import BeautifulSoup

# ---------- helpers: 提取 next/内嵌 JSON 文本 ----------
def _extract_next_json_chunks(html: str) -> str:
    # 直接用正则在 HTML 文本里找包含关键字段的大块 JSON
    # 尽量保守：用最小匹配 + 关键锚点
    m = re.search(r'"gender":"(?:Mens|Womens|Girls|Boys)".{0,2000}?"variants":\[(.*?)\]\}', html, re.S)
    if m: 
        return m.group(0)
    # 兜底：找包含 sizes.allSizes 的块
    m = re.search(r'"sizes":\{"allSizes":\[(.*?)\]\}', html, re.S)
    return m.group(0) if m else ""

def _extract_color_from_og_alt(soup: BeautifulSoup) -> str:
    # 取第一个 og:image:alt，形如 "Black BK11 - Barbour International - xxx"
    for tag in soup.find_all("meta", {"property": "og:image:alt"}):
        content = (tag.get("content") or "").strip()
        if content:
            # 颜色名 = 第一个 " - " 之前，再去掉末尾的色码
            first = content.split(" - ", 1)[0]  # e.g. "Black BK11"
            # 去掉类似 BK11/NY91 这类色码
            first = re.sub(r"\b[A-Z]{2}\d{2,}\b", "", first).strip()
            if first:
                return first
    return ""

def _extract_all_sizes(html: str):
    """
    返回 list[str]，来自 sizes.allSizes[].size。
    """
    sizes = []
    ms = re.search(r'"sizes"\s*:\s*\{\s*"allSizes"\s*:\s*(\[[^\]]*\])', html, re.S | re.I)
    if ms:
        try:
            arr = json.loads(ms.group(1))
            for it in arr:
                s = (it.get("size") or "").strip()
                if s:
                    sizes.append(s)
        except Exception:
            pass
    return sizes


def _extract_sizes_dom_fallback(soup: BeautifulSoup):
    """
    从渲染后的尺寸按钮容器抓取：
    - data-testid="swatch-button-enabled" => 有货
    - data-testid="swatch-button-disabled" => 无货
    - 有些站不渲染 disabled 按钮，此时只拿到 enabled 的那部分
    """
    enabled = set()
    disabled = set()

    # 启用按钮
    for btn in soup.select('[data-testid="swatch-button-enabled"]'):
        val = (btn.get("value") or btn.get_text() or "").strip()
        if val:
            enabled.add(re.sub(r"\s+", " ", val))

    # 禁用按钮（如果渲染）
    for btn in soup.select('[data-testid="swatch-button-disabled"], button[disabled][data-testid*="swatch"]'):
        val = (btn.get("value") or btn.get_text() or "").strip()
        if val:
            disabled.add(re.sub(r"\s+", " ", val))

    if not enabled and not disabled:
        return []

    # 如果禁用没渲染出来，就只返回 enabled，其他交给 allSizes 合并逻辑补无货
    entries = [(s, "有货") for s in sorted(enabled, key=lambda x: (len(x), x))]
    entries += [(s, "无货") for s in sorted(disabled, key=lambda x: (len(x), x))]
    return entries



def _extract_color_gender_from_json(html: str) -> (str, str):
    block = _extract_next_json_chunks(html)
    color = ""
    gender = ""
    if block:
        mc = re.search(r'"color"\s*:\s*"([^"]+)"', block)
        if mc:
            raw = mc.group(1)  # e.g. "Black BK11"
            color = re.sub(r"\b[A-Z]{2}\d{2,}\b", "", raw).strip()
        mg = re.search(r'"gender"\s*:\s*"(Mens|Womens|Girls|Boys)"', block)
        if mg:
            g = mg.group(1).lower()
            # 统一到你原来 TXT 习惯（men / women），也可输出 mens/womens
            mapping = {"mens":"men", "womens":"women", "girls":"women", "boys":"men"}
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
    常见前缀（Barbour/International）：
      男款：MQU, MWX, MSH, MKN, MGL, MFL, MGI, MLI, MSW, MCA...
      女款：LQU, LWX, LSH, LKN, LGL, LFL, LGI, LLI, LSW, LCA...
    返回：men / women / No Data
    """
    if not code:
        return "No Data"
    c = code.strip().upper()
    # 先看首字母
    if c.startswith("M"):
        return "men"
    if c.startswith("L"):
        return "women"
    # 再看常见 3 位前缀（更精确）
    male3  = ("MQU", "MWX", "MSH", "MKN", "MGL", "MFL", "MGI", "MLI", "MSW", "MCA")
    female3= ("LQU", "LWX", "LSH", "LKN", "LGL", "LFL", "LGI", "LLI", "LSW", "LCA")
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
    # 如你以后想区分童款，可在这扩展：
    if g in ("boys", "boy"):
        return "男款"   # 或者返回 "童款-男"
    if g in ("girls", "girl"):
        return "女款"   # 或者返回 "童款-女"
    return "No Data"


def _extract_gender_new(soup: BeautifulSoup, html: str, url: str) -> str:
    """
    优先从整页 JSON 中抽取 "gender":"Mens|Womens|Boys|Girls"；
    若没有，再从面包屑/标题/描述里推断；最后用 URL 兜底。
    返回：men / women / No Data
    """
    # 1) JSON（整页任意位置）
    m = re.search(r'"gender"\s*:\s*"(Mens|Womens|Girls|Boys)"', html, re.I)
    if m:
        g = m.group(1).lower()
        mapping = {"mens": "men", "womens": "women", "girls": "women", "boys": "men"}
        return mapping.get(g, g)

    # 2) 面包屑/标题/描述 推断
    # （尽量不依赖你其他函数，避免命名冲突）
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

    # 3) URL 兜底
    ul = (url or "").lower()
    if "/women" in ul or "womens" in ul:
        return "women"
    if "/men" in ul or "mens" in ul:
        return "men"

    return "No Data"



# ---------- sizes & availability ----------
def _extract_sizes_from_variants(html: str):
    """
    返回 list[(size, status)]，仅包含 variants 里出现的尺码；
    status = "有货"/"无货"（以 isOnStock 为准）。
    """
    entries = []
    # 放宽匹配范围，确保 "size" 和 "isOnStock" 不同层也能命中
    patt = r'"size"\s*:\s*"([^"]+?)".{0,4000}?"isOnStock"\s*:\s*(true|false)'
    for m in re.finditer(patt, html, re.S | re.I):
        size = m.group(1).strip()
        avail = (m.group(2).lower() == "true")
        if size:
            entries.append((size, "有货" if avail else "无货"))
    return entries



def _extract_sizes_from_allSizes(html: str):
    # 兜底：没有 isOnStock，就认为页面在售 → 记为有货
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

def _extract_sizes_new(soup: BeautifulSoup, html: str):
    """
    统一出口：
    1) allSizes = 全量尺码
    2) 有货集合 = variants(isOnStock=true) ∪ DOM-enabled
    3) 不在有货集合但在 allSizes 的 => 无货
    4) 如果 allSizes 为空：仅用 DOM（有则有，无则 No Data）
    """
    all_sizes = _extract_all_sizes(html)
    var_entries = _extract_sizes_from_variants(html)  # 只含出现在 variants 的尺码
    dom_entries = _extract_sizes_dom_fallback(soup)

    instock_from_variants = {s for s, st in var_entries if st == "有货"}
    instock_from_dom = {s for s, st in dom_entries if st == "有货"}
    oos_from_dom = {s for s, st in dom_entries if st == "无货"}

    # 1) 有全量尺码时：按集合标记
    if all_sizes:
        in_stock = set()
        in_stock |= instock_from_variants
        in_stock |= instock_from_dom

        # 按页面显示的自然顺序输出（不强行排序）
        by_size = {}
        ordered = []
        for s in all_sizes:
            s_norm = re.sub(r"\s+", " ", s).strip()
            if not s_norm:
                continue
            status = "有货" if s_norm in in_stock else "无货"
            by_size[s_norm] = status
            ordered.append(s_norm)

        EAN = "0000000000000"
        product_size        = ";".join(f"{s}:{by_size[s]}" for s in ordered) or "No Data"
        product_size_detail = ";".join(f"{s}:{3 if by_size[s]=='有货' else 0}:{EAN}" for s in ordered) or "No Data"
        return product_size, product_size_detail

    # 2) 没有 allSizes：退回 DOM/variants 的并集
    if var_entries or dom_entries:
        merged = {}
        order = []
        for s, st in (var_entries + dom_entries):
            s_norm = re.sub(r"\s+", " ", s).strip()
            if not s_norm:
                continue
            # 有货优先覆盖无货
            if (s_norm not in merged) or (merged[s_norm] == "无货" and st == "有货"):
                merged[s_norm] = st
                if s_norm not in order:
                    order.append(s_norm)

        EAN = "0000000000000"
        product_size        = ";".join(f"{s}:{merged[s]}" for s in order) or "No Data"
        product_size_detail = ";".join(f"{s}:{3 if merged[s]=='有货' else 0}:{EAN}" for s in order) or "No Data"
        return product_size, product_size_detail

    return "No Data", "No Data"




def _normalize_url(u: str) -> str:
    return u.strip() if u else ""

def get_dbapi_connection(conn_or_engine):
    if hasattr(conn_or_engine, "cursor"): return conn_or_engine
    if hasattr(conn_or_engine, "raw_connection"): return conn_or_engine.raw_connection()
    c = getattr(conn_or_engine, "connection", None)
    if c is not None:
        dbapi = getattr(c, "dbapi_connection", None)
        if dbapi is not None and hasattr(dbapi, "cursor"): return dbapi
        inner = getattr(c, "connection", None)
        if inner is not None and hasattr(inner, "cursor"): return inner
        if hasattr(c, "cursor"): return c
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
        try: raw_conn.rollback()
        except Exception: pass
    return cache

def build_url_code_cache(raw_conn, products_table: str, offers_table: Optional[str], site_name: str):
    """启动时构建一次 URL→ProductCode 映射缓存。"""
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

# ================== 文件写入/模板 ==================
def _atomic_write_bytes(data: bytes, dst: Path, retries: int = 6, backoff: float = 0.25) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=str(dst.parent),
                                             prefix=".tmp_", suffix=f".{os.getpid()}.{threading.get_ident()}") as tf:
                tmp = Path(tf.name)
                tf.write(data); tf.flush(); os.fsync(tf.fileno())
            try:
                os.replace(tmp, dst)
            finally:
                if tmp and tmp.exists():
                    try: tmp.unlink(missing_ok=True)
                    except Exception: pass
            return True
        except Exception:
            if dst.exists(): return True
            time.sleep(backoff * (i + 1))
            try:
                if tmp and tmp.exists(): tmp.unlink(missing_ok=True)
            except Exception:
                pass
    return dst.exists()

def _kv_txt_bytes(info: Dict[str, Any]) -> bytes:
    # ✨ 保持与旧版完全一致的 KV 输出字段顺序
    fields = [
        "Product Code", "Product Name", "Product Description", "Product Gender",
        "Product Color", "Product Price", "Adjusted Price", "Product Material",
        "Style Category", "Feature", "Product Size", "Product Size Detail",
        "Source URL", "Site Name"
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
    if not s: return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s.replace(",", ""))
    return float(m.group(1)) if m else None

# ================== 等待水合 ==================
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
    key_css = ", ".join([
        # price/title
        "[data-testid*='price']","[data-component*='price']","[itemprop='price']","meta[itemprop='price']",
        "h1","[data-testid*='title']","[data-component*='title']",
        # sizes
        "button[aria-pressed][data-testid*='size']","li[role='option']","div[role='option']",
        "option[data-testid*='drop-down-option']","#sizeDdl option",
        # JSON-LD
        "script[type='application/ld+json']",
    ])
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.find_elements(By.CSS_SELECTOR, key_css):
                return True
        except Exception:
            pass
        _soft_scroll(driver, steps=2, pause=0.45)
    return False

# ================== JSON-LD 解析 ==================
def _pick_first(x):
    if isinstance(x, list) and x: return x[0]
    return x

def parse_jsonld(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        txt = (tag.string or tag.text or "").strip()
        if not txt: continue
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
            if not isinstance(node, dict): continue
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
        if isinstance(brand, dict): out["brand"] = brand.get("name")
        else: out["brand"] = brand
        imgs = product.get("image") or []
        if isinstance(imgs, str): imgs = [imgs]
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
    if price: out["price"] = str(price)
    if currency: out["currency"] = currency
    if availability:
        out["availability"] = availability.split("/")[-1] if "/" in availability else availability
    if url: out["url"] = url
    return out

# ================== 性别/颜色/尺码（加固版） ==================
GENDER_WORDS = (
    ("Womens", ("womens", "women", "ladies", "women's", "lady")),
    ("Mens",   ("mens", "men", "men's", "man")),
    ("Boys",   ("boys", "boy")),
    ("Girls",  ("girls", "girl")),
)
COLOR_WORDS = [
    "Black","Navy","Green","Olive","Brown","Blue","Red","Cream","Beige","Grey","Gray",
    "White","Pink","Burgundy","Khaki","Stone","Tan","Orange","Yellow","Purple"
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
    if g != "No Data": return g
    m = re.search(r'"gender"\s*:\s*"(?P<g>Womens|Mens|Boys|Girls)"', html, re.I)
    if m: return m.group("g").capitalize()
    return _infer_gender_from_text(desc, title)

def _extract_color(html: str, soup: BeautifulSoup, title: str) -> str:
    el = soup.select_one("[data-testid*='colour'] [data-testid*='value'], [data-component*='colour'], [aria-label*='Colour'] [aria-live]")
    if el:
        c = el.get_text(strip=True)
        if c: return c
    m = re.search(r'"color"\s*:\s*"([A-Za-z /-]{3,20})"', html)
    if m: return m.group(1).strip()
    for w in COLOR_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", title, re.I):
            return w
    return "No Data"

def _extract_sizes_legacy_dropdown(soup: BeautifulSoup) -> Tuple[str, str]:
    entries = []

    # 1) 按钮
    for btn in soup.select("button[aria-pressed][data-testid*='size'], button[aria-pressed][aria-label*='Size']"):
        lab = (btn.get_text() or btn.get("aria-label") or "").strip()
        if not lab: continue
        disabled = (btn.get("disabled") is not None) or (btn.get("aria-disabled") in ("true", "True"))
        status = "无货" if disabled else "有货"
        entries.append((lab, status))

    # 2) 列表/可选项
    for node in soup.select("li[role='option'], div[role='option']"):
        lab = (node.get_text() or node.get("aria-label") or "").strip()
        if not lab: continue
        if lab.lower().startswith(("select size", "choose size")):
            continue
        disabled = node.get("aria-disabled") in ("true", "True") or "disabled" in (node.get("class") or [])
        status = "无货" if disabled else "有货"
        entries.append((lab, status))

    # 3) 下拉
    for opt in soup.select("select option[data-testid*='drop-down-option'], #sizeDdl option"):
        lab = (opt.get_text() or "").strip()
        if not lab or lab.lower().startswith(("select", "choose")):
            continue
        clean = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", lab, flags=re.I).strip(" -/")
        disabled = opt.has_attr("disabled") or (opt.get("aria-disabled") == "true") or "out of stock" in lab.lower()
        status = "无货" if disabled else "有货"
        entries.append((clean or lab, status))

    # 4) 兜底：形似尺码的按钮
    if not entries:
        for btn in soup.select("button, [role='option']"):
            lab = (btn.get_text() or getattr(btn, "get", lambda *_: None)("aria-label") or "").strip()
            if not lab: continue
            if re.search(r"\b\d{1,2}(\s*\([A-Z0-9]+\))?$", lab):
                disabled = hasattr(btn, "get") and (btn.get("disabled") is not None or btn.get("aria-disabled") == "true")
                status = "无货" if disabled else "有货"
                entries.append((lab, status))

    if not entries:
        return "No Data", "No Data"

    ordered = []
    seen = {}
    for label, status in entries:
        label = re.sub(r"\s+", " ", label).strip()
        if label not in seen or (seen[label] == "无货" and status == "有货"):
            seen[label] = status
            if label not in ordered: ordered.append(label)

    EAN = "0000000000000"
    product_size        = ";".join(f"{s}:{seen[s]}" for s in ordered) or "No Data"
    product_size_detail = ";".join(f"{s}:{3 if seen[s]=='有货' else 0}:{EAN}" for s in ordered) or "No Data"
    return product_size, product_size_detail

def _from_jsonld_product_new(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    从 JSON-LD 提取最核心的产品元数据（name/description/sku）。
    注意：此函数与 parse_jsonld 的字段命名对齐：name/description/sku。
    """
    out = {"name": None, "description": None, "sku": None}

    # 直接复用已存在的 parse_jsonld：把 soup 转成 html 再解析
    try:
        html = str(soup)
        jd = parse_jsonld(html) or {}
    except Exception:
        jd = {}

    # parse_jsonld 返回的是 title/description/sku，这里做一次字段对齐
    title = jd.get("title")
    if title:
        out["name"] = title
    if jd.get("description"):
        out["description"] = jd["description"]
    if jd.get("sku"):
        out["sku"] = jd["sku"]

    # 兜底：没有拿到 name 时，用 <h1> 或 <title>
    if not out["name"]:
        h1 = soup.select_one("h1,[data-testid*='title'],[data-component*='title']")
        out["name"] = h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else None)

    return out

def _extract_prices_new(soup: BeautifulSoup, html: str) -> Tuple[Optional[float], Optional[float]]:
    """
    返回 (current_price, original_price)
    - current_price：当前展示价（常为折后价）
    - original_price：原价（ticket/was/rrp）
    逻辑：JSON-LD 的 price 作为“当前价”优先；原价从 DOM 的 ticket/was 节点兜底。
    """
    current_price = None
    original_price = None

    # 1) JSON-LD 的价格作为当前价
    try:
        jd = parse_jsonld(html) or {}
        if jd.get("price"):
            current_price = float(str(jd["price"]).replace(",", ""))
    except Exception:
        pass

    # 2) DOM 里找原价（ticket/was/rrp）
    was_el = soup.select_one(
        "[data-testid*='ticket-price'], [data-component*='ticket'], .price-was, .wasPrice, .rrp"
    )
    if was_el:
        original_price = _to_num(was_el.get_text(" ", strip=True))

    # 3) 若缺失，互相兜底
    if original_price is None and current_price is not None:
        original_price = current_price
    if current_price is None:
        # 再尝试从可见价格块取一次“当前价”
        cur_el = soup.select_one("[data-testid*='price'], [data-component*='price'], [itemprop='price'], meta[itemprop='price']")
        if cur_el:
            if getattr(cur_el, "name", "") == "meta":
                current_price = _to_num(cur_el.get("content") or "")
            else:
                current_price = _to_num(cur_el.get_text(" ", strip=True))
        # 仍然没有就退回原价
        if current_price is None and original_price is not None:
            current_price = original_price

    return current_price, original_price

# ================== 核心解析 ==================
def parse_info_new(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    jd = _from_jsonld_product_new(soup) or {}

    title = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc  = jd.get("description") or "No Data"

    curr, orig = _extract_prices_new(soup, html)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr

    # >>> 新增：颜色/性别/尺码 <<<
    color  = _extract_color_new(soup, html)
    gender = _extract_gender_new(soup, html, url)
    product_size, product_size_detail = _extract_sizes_new(soup, html)

    info = {
        "Product Code": jd.get("sku") or "No Data",   # 这里仍是组合 SKU（如 321534）；精确编码仍交由你现有的 DB 匹配逻辑
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color or "No Data",
        "Product Price": f"{orig:.2f}" if isinstance(orig, (int, float)) else "No Data",
        "Adjusted Price": f"{curr:.2f}" if isinstance(curr, (int, float)) else "No Data",
        "Product Material": "No Data",
        "Style Category": "casual wear",
        "Feature": "No Data",
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Source URL": url,
        "Site Name": SITE_NAME,
    }
    return info


# ================== Selenium 基础 ==================
def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless: options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=en-GB")
    options.add_argument("accept-language=en-GB,en-US;q=0.9,en;q=0.8")
    return uc.Chrome(options=options)

def fetch_product_info_with_single_driver(driver, url: str) -> Dict[str, Any]:
    driver.get(url)
    ok = wait_pdp_ready(driver, timeout=WAIT_HYDRATE_SECONDS)
    if not ok:
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="timeout_debug")
        return parse_info_new(html, url)
    _soft_scroll(driver, steps=6, pause=0.4)
    html = driver.page_source or ""
    _dump_debug_html(html, url, tag="debug_new")
    return parse_info_new(html, url)

# ================== 处理单个 URL ==================
def process_url_with_driver(driver, url: str, conn: Connection, delay: float = DEFAULT_DELAY) -> Path | None:
    print(f"\n🌐 正在抓取: {url}")
    info = fetch_product_info_with_single_driver(driver, url)

    # 先查 URL→Code 缓存（命中则不做匹配）
    norm_url = _normalize_url(url)
    code = URL_CODE_CACHE.get(norm_url)

        # ……（已有匹配 code 的逻辑在这之前）
    # 此时 code 变量已经确定，info 也已经填好

    # ★ gender 兜底：有 code 才兜底；无 code 则保持 No Data（不发布）
    if (not info.get("Product Gender")) or (info.get("Product Gender") == "No Data"):
        g_from_code = _infer_gender_from_code(code or info.get("Product Code"))
        if g_from_code != "No Data":
            info["Product Gender"] = g_from_code




    if code:
        print(f"🔗 缓存命中 URL→{code}")
        info["Product Code"] = code
    else:
        # 模糊匹配（沿用旧阈值/逻辑）
        raw_conn = get_dbapi_connection(conn)
        title = info.get("Product Name") or ""
        color = info.get("Product Color") or ""
        results = match_product(
            raw_conn,
            scraped_title=title, scraped_color=color,
            table=PRODUCTS_TABLE,
            name_weight=NAME_WEIGHT, color_weight=COLOR_WEIGHT,
            type_weight=(1.0 - NAME_WEIGHT - COLOR_WEIGHT),
            topk=5, recall_limit=2000, min_name=0.92, min_color=0.85,
            require_color_exact=False, require_type=False,
        )
        code = choose_best(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
        print("🔎 match debug")
        print(f"  raw_title: {title}")
        print(f"  raw_color: {color}")
        txt, why = explain_results(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
        print(txt)
        if code:
            print(f"  ⇒ ✅ choose_best = {code}")
            info["Product Code"] = code
        else:
            print(f"  ⇒ ❌ no match ({why})")
            if results:
                top3 = " | ".join(f"{r['product_code']}[{r['score']:.3f}]" for r in results[:3])
                print("🧪 top:", top3)

    # 输出 TXT
    if code:
        out_path = TXT_DIR / f"{code}.txt"
    else:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        safe_name = _safe_name(info.get("Product Name") or "BARBOUR")
        out_path = TXT_DIR / f"{safe_name}_{short}.txt"

    info["Product Gender"] = _gender_to_cn(info.get("Product Gender"))

    
    payload = _kv_txt_bytes(info)
    ok = _atomic_write_bytes(payload, out_path)
    if ok:
        print(f"✅ 写入: {out_path} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")

    if delay > 0:
        time.sleep(delay)
    return out_path

# ================== 主入口 ==================
def houseoffraser_fetch_info(max_workers: int = MAX_WORKERS_DEFAULT, delay: float = DEFAULT_DELAY, headless: bool = False):
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return
    raw_urls = [line.strip() for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")]

    # 规范化去重（保序）
    seen = set(); urls = []
    for u in raw_urls:
        nu = _normalize_url(u)
        if nu in seen: continue
        seen.add(nu); urls.append(u)

    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0: return

    engine_url = f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['dbname']}"
    engine = create_engine(engine_url)

    # 构建 URL→Code 缓存
    with engine.begin() as conn:
        raw = get_dbapi_connection(conn)
        build_url_code_cache(raw, PRODUCTS_TABLE, OFFERS_TABLE, SITE_NAME)

    # 单实例浏览器：首个商品页先给你10秒点 Cookie
    driver = get_driver(headless=headless)
    try:
        if urls:
            print("🕒 将打开首个商品页。请在 10 秒内手动点击 Cookie 的 'Allow all' 按钮...")
            driver.get(urls[0])
            time.sleep(10)
            print("✅ 已等待 10 秒，开始正式抓取")

        ok, fail = 0, 0
        with engine.begin() as conn:
            for idx, u in enumerate(urls, start=1):
                print(f"[启动] [{idx}/{total}] {u}")
                try:
                    path = process_url_with_driver(driver, u, conn=conn, delay=delay)
                    ok += 1 if path else 0
                    print(f"[完成] [{idx}/{total}] {u} -> {path}")
                except Exception as e:
                    fail += 1
                    print(f"[失败] [{idx}/{total}] ❌ {u}\n    {repr(e)}")

        print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")

    finally:
        try: driver.quit()
        except Exception: pass


if __name__ == "__main__":
    houseoffraser_fetch_info()
