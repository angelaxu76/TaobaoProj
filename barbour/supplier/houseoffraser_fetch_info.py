# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour 商品抓取（支持新版/旧版）
- 预加载 URL→ProductCode 缓存（仅启动时一次）
- “猎取 legacy”模式：每次尝试新建 driver；若是 new/unknown 立刻放弃并重试，最多 10 次；没命中则记录 URL
- 命中 legacy → 解析 → (缓存命中编码 or 模糊匹配) → 写 TXT
- 所有调试/输出原子写，避免并发文件冲突
"""

from __future__ import annotations

import os, re, json, time, tempfile, threading, html as ihtml
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# ====== 浏览器 & 解析 ======
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ====== 项目依赖（按你的工程保持不变）======
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from config import BARBOUR, BRAND_CONFIG
from barbour.core.site_utils import assert_site_or_raise as canon
from barbour.core.sim_matcher import match_product, choose_best, explain_results
from common_taobao.size_utils import clean_size_for_barbour as _norm_size  # 统一尺码清洗

# ================== 站点与目录 ==================
SITE_NAME = canon("houseoffraser")
LINKS_FILE: str = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR: Path = TXT_DIR / "_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS_TABLE: str = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE: Optional[str] = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")  # 允许不存在
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# ================== 参数 ==================
WAIT_PRICE_SECONDS = 12
DEFAULT_DELAY = 0.0
MAX_WORKERS_DEFAULT = 4
MIN_SCORE = 0.72
MIN_LEAD = 0.04
NAME_WEIGHT = 0.75
COLOR_WEIGHT = 0.25

# ================== 并发写入去重标记（仅标记，不阻止覆盖） ==================
_WRITTEN: set[str] = set()
_WRITTEN_LOCK = threading.Lock()

# ================== URL 规范化 & 预加载缓存 ==================
from urllib.parse import urlparse, parse_qsl, urlunparse, urlencode
from collections import OrderedDict

URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False



# ====== 标准尺码表（用于补齐未出现尺码=0） ======
WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（不含 52）

def _full_order_for_gender(gender: str) -> list[str]:
    """根据性别返回完整尺码顺序；未知/童款默认按男款处理。"""
    g = (gender or "").lower()
    if "女" in g or "women" in g or "lady" in g or "ladies" in g:
        return WOMEN_ORDER
    # 默认按男款；童款/未知也先按男款处理（若后续要定制，再细化）
    return MEN_ALPHA_ORDER + MEN_NUM_ORDER



def _normalize_url(u: str) -> str:
    """保持原样，不做任何清理或去重"""
    return u.strip() if u else ""

def get_dbapi_connection(conn_or_engine):
    # 取得 DBAPI 连接以便 cursor() 调用
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
    """执行 SQL 并将 (url, code) 写入 cache；发生错误自动 rollback，不抛出。"""
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
    """
    启动时构建一次 URL→ProductCode 映射缓存：
      1) 优先从 offers 表读取 site_name=houseoffraser 的 URL+Code
      2) 再从 products 表补充（历史人工回填）
    """
    global URL_CODE_CACHE, _URL_CODE_CACHE_READY
    if _URL_CODE_CACHE_READY:
        return URL_CODE_CACHE

    cache = OrderedDict()

    # 1) offers 表（可选）：不同项目可能字段不同，这里尝试常见列组合
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

    # 2) products 表（固定有 product_code）
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

# ================== 文件原子写 ==================
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
                os.replace(tmp, dst)  # Windows 原子替换（同分区）
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

# ================== 栈判定 ==================
def _classify_stack_by_html_head(html: str) -> str:
    """返回 'legacy' / 'new' / 'unknown'，仅看首屏特征。"""
    head = html[:8192].lower()
    # Next.js / 新栈特征
    if ('id="__next' in head) or ('id="__next_data__"' in head) or ("__next" in head) or ("/_next/static/" in head) or ("next-data" in head):
        return "new"
    if ('data-testid="product-price"' in head) or ('data-component="price"' in head):
        return "new"
    # 旧栈常见资源路径/变量
    if ("/wstatic/dist/" in head) or ('xmlns="http://www.w3.org/1999/xhtml"' in head) or ('var datalayerdata' in head):
        return "legacy"
    if ("add-to-bag" in head and "house of fraser" in head):
        return "legacy"
    return "unknown"

# ================== 旧版解析（保持你当前逻辑） ==================
def _extract_title_legacy(soup: BeautifulSoup) -> str:
    t = _clean(soup.title.get_text()) if soup.title else "No Data"
    t = re.sub(r"\s*\|\s*House of Fraser\s*$", "", t, flags=re.I)
    return t or "No Data"

def _extract_desc_legacy(soup: BeautifulSoup) -> str:
    m = soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"): return _clean(m.get("content"))
    m2 = soup.find("meta", attrs={"name": "description"})
    if m2 and m2.get("content"): return _clean(m2.get("content"))
    try:
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            txt = (tag.get_text() or "").strip()
            if not txt: continue
            data = json.loads(txt); items = data if isinstance(data, list) else [data]
            for obj in items:
                if not isinstance(obj, dict): continue
                if obj.get("@type") == "Product" and obj.get("description"): return _clean(str(obj["description"]))
                if isinstance(obj.get("@graph"), list):
                    for node in obj["@graph"]:
                        if isinstance(node, dict) and node.get("@type") == "Product" and node.get("description"):
                            return _clean(str(node["description"]))
    except Exception:
        pass
    return "No Data"

def _extract_color_legacy(soup: BeautifulSoup) -> str:
    import re as _re
    def norm(s: str) -> str: return _re.sub(r"\s+", " ", s).strip()
    n = soup.select_one("#colourName")
    if n:
        t = norm(n.get_text(" ", strip=True))
        if t: return t
    sel = soup.select_one("#ulColourImages li[aria-checked='true'], #ulColourImages li.variantHighlight[aria-checked='true']")
    if sel:
        t = sel.get("data-text") or sel.get("title")
        if not t:
            img = sel.find("img"); t = (img.get("alt") if img else None)
        if t: return norm(t)
    opt = soup.select_one("#sizeDdl option[selected]")
    if opt and opt.get("title"):
        m = _re.search(r"Select Size\s+(.+?)\s+is out of stock", opt["title"], _re.I)
        if m: return norm(m.group(1))
    colvar = None
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        txt = (tag.string or tag.get_text() or "")
        m = _re.search(r"/images/products/(\d{5,})_l\.[a-z]+", txt)
        if m: colvar = m.group(1); break
    if colvar:
        li = soup.select_one(f"#ulColourImages li[data-colvarid='{colvar}'], #ulColourImages li[id$='{colvar}']")
        if li:
            t = li.get("data-text") or li.get("title")
            if not t:
                img = li.find("img"); t = (img.get("alt") if img else None)
            if t: return norm(t)
    return "No Data"

def _extract_gender_legacy(title: str, soup: BeautifulSoup) -> str:
    t = (title or "").lower()
    if "women" in t: return "女款"
    if "men" in t:   return "男款"
    if any(k in t for k in ["kids", "girls", "boys", "junior", "juniors"]): return "童款"
    return "No Data"

def _extract_prices_legacy(soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
    sp = soup.select_one("#lblSellingPrice")
    curr = _to_num(sp.get_text(" ", strip=True)) if sp else None
    orig = None
    for t in soup.select("#lblTicketPrice, .originalTicket"):
        val = _to_num(t.get_text(" ", strip=True))
        if val is not None: orig = val; break
    if orig is None:
        blocks = soup.select(".originalprice, .price-was, .wasPrice, .priceWas, .rrp, .ticketPrice, .pdpPriceRating, .sticky-atb--price")
        for b in blocks:
            m = re.search(r"£\s*([0-9]+(?:\.[0-9]{1,2})?)", b.get_text(" ", strip=True))
            if m:
                val = _to_num(m.group(0))
                if curr is not None and val == curr: continue
                orig = val; break
    if orig is None:
        try:
            for tag in soup.find_all("script"):
                txt = (tag.string or tag.get_text() or "").strip()
                if not txt or ("RefPrice" not in txt and "RefPriceRaw" not in txt): continue
                m_raw = re.search(r'RefPriceRaw"\s*:\s*([0-9]+(?:\.[0-9]{1,2})?)', txt)
                m_fmt = re.search(r'RefPrice"\s*:\s*"£\s*([0-9]+(?:\.[0-9]{1,2})?)', txt)
                if m_raw: orig = _to_num(m_raw.group(1)); break
                if m_fmt: orig = _to_num(m_fmt.group(0)); break
        except Exception:
            pass
    if curr is None:
        tw = soup.find("meta", attrs={"name": "twitter:data1"})
        if tw and tw.get("content"): curr = _to_num(tw.get("content"))
    if curr is None:
        price_block = soup.select_one(".pdpPriceRating, .pdpPrice") or soup
        m = re.search(r"£\s*([0-9]+(?:\.[0-9]{1,2})?)", price_block.get_text(" ", strip=True))
        if m: curr = _to_num(m.group(0))
    if orig is None:
        html = soup.decode()
        m_raw = re.search(r'RefPriceRaw"\s*:\s*([0-9]+(?:\.[0-9]{1,2})?)', html)
        m_fmt = re.search(r'RefPrice"\s*:\s*"£\s*([0-9]+(?:\.[0-9]{1,2})?)', html)
        if m_raw: orig = _to_num(m_raw.group(1))
        elif m_fmt: orig = _to_num(m_fmt.group(0))
    if curr is not None and orig is None: orig = curr
    if orig is not None and curr is None: curr = orig
    return curr, orig

def _extract_size_pairs_legacy(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    sel = soup.find("select", id="sizeDdl")
    entries = []
    if not sel:
        return entries
    for opt in sel.find_all("option"):
        raw_label = (opt.get_text() or "").strip()
        if not raw_label or raw_label.lower().startswith("select"):
            continue
        title = (opt.get("title") or "").lower()
        cls = " ".join(opt.get("class") or []).lower()
        raw_lc = raw_label.lower()
        oos = (
            "out of stock" in raw_lc
            or "out of stock" in title
            or "greyout" in cls
            or opt.has_attr("disabled")
        )
        status = "无货" if oos else "有货"
        clean_label = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", raw_label, flags=re.I).strip(" -/")
        size_norm = _norm_size(clean_label)
        if not size_norm:
            continue
        entries.append((size_norm, status))
    return entries

def _build_size_lines_legacy(pairs: List[Tuple[str, str]], gender: str) -> Tuple[str, str]:
    by_size: Dict[str, str] = {}

    # 记录出现的尺码；同尺码多次时“有货优先”
    for size, status in pairs:
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            by_size[size] = status

    # ★ 按已出现的尺码决定男款用哪一系；女款固定 4–20
    chosen = _choose_full_order_for_gender(gender, set(by_size.keys()))

    # 清理掉另一系里误混入的键，避免混用
    for k in list(by_size.keys()):
        if k not in chosen:
            by_size.pop(k, None)

    # 补齐“未出现”的尺码为 无货/0（仅在选定系内）
    for s in chosen:
        if s not in by_size:
            by_size[s] = "无货"

    EAN = "0000000000000"
    ordered = list(chosen)
    ps  = ";".join(f"{k}:{by_size[k]}" for k in ordered) or "No Data"
    psd = ";".join(f"{k}:{3 if by_size[k]=='有货' else 0}:{EAN}" for k in ordered) or "No Data"
    return ps, psd



# ================== 新版解析骨架（保持你现有实现/可按需细化） ==================

def _choose_full_order_for_gender(gender: str, present: set[str]) -> list[str]:
    """男款在【字母系】与【数字系】二选一；女款固定 4–20。"""
    g = (gender or "").lower()
    if "女" in g or "women" in g or "lady" in g or "ladies" in g:
        return WOMEN_ORDER[:]  # 4..20

    has_num   = any(k in MEN_NUM_ORDER   for k in present)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in present)
    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]          # 30..50（不含 52）
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]        # 2XS..3XL
    if has_num or has_alpha:
        num_count   = sum(1 for k in present if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in present if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]
    # 实在判不出来，默认用字母系更稳妥
    return MEN_ALPHA_ORDER[:]



def _clean_html_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = ihtml.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def _from_jsonld_product_new(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for sc in soup.find_all("script", {"type": "application/ld+json"}):
        txt = sc.string or ""
        try:
            data = json.loads(txt)
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "Product":
                continue
            out["name"] = obj.get("name")
            out["description"] = _clean_html_text(obj.get("description", ""))
            out["sku"] = obj.get("sku") or obj.get("gtin8")
            return out
    return out

def _extract_prices_new(soup: BeautifulSoup, html_text: str) -> Tuple[Optional[float], Optional[float]]:
    # 保留原兜底逻辑；生产时尽量走 legacy，不依赖此分支
    nums: List[float] = []
    for tag in soup.find_all(attrs={"data-testvalue": True}):
        v = tag.get("data-testvalue")
        try:
            n = float(v) / 100.0
            nums.append(n)
        except Exception:
            pass
    t = soup.find(attrs={"data-testid": "ticket-price"})
    if t:
        val = _to_num(t.get_text())
        if val is not None:
            nums.append(val)
    if not nums:
        m1 = re.search(r'"SellPriceRaw"\s*:\s*([0-9]+(?:\.[0-9]{1,2})?)', html_text)
        if m1:
            try: nums.append(float(m1.group(1)))
            except: pass
        m2 = re.search(r'"RefPriceRaw"\s*:\s*([0-9]+(?:\.[0-9]{1,2})?)', html_text)
        if m2:
            try: nums.append(float(m2.group(1)))
            except: pass
    nums = sorted(set(x for x in nums if x is not None))
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    return nums[0], nums[-1]

def _extract_sizes_new(soup: BeautifulSoup, gender: str) -> Tuple[str, str]:
    entries = []
    for opt in soup.find_all("option", attrs={"data-testid": "drop-down-option"}):
        val = (opt.get("value") or "").strip()
        if not val:
            continue
        raw_label = (opt.get_text() or "").strip()
        clean_label = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", raw_label, flags=re.I).strip(" -/")
        size_norm = _norm_size(clean_label)
        if not size_norm:
            continue
        oos = opt.has_attr("disabled") or (opt.get("aria-disabled") == "true") or "out of stock" in raw_label.lower()
        status = "无货" if oos else "有货"
        entries.append((size_norm, status))

    if not entries:
        return "No Data", "No Data"

    by_size: Dict[str, str] = {}
    for size, status in entries:
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            by_size[size] = status

    # ★ 关键：和 legacy 一样，按出现的尺码决定男款系别
    chosen = _choose_full_order_for_gender(gender, set(by_size.keys()))

    # 清理混系
    for k in list(by_size.keys()):
        if k not in chosen:
            by_size.pop(k, None)

    # 补齐 0
    for s in chosen:
        if s not in by_size:
            by_size[s] = "无货"

    EAN = "0000000000000"
    ordered = list(chosen)
    product_size = ";".join(f"{s}:{by_size[s]}" for s in ordered) or "No Data"
    product_size_detail = ";".join(f"{s}:{3 if by_size[s]=='有货' else 0}:{EAN}" for s in ordered) or "No Data"
    return product_size, product_size_detail



def parse_info_legacy(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title_legacy(soup)
    desc  = _extract_desc_legacy(soup)
    color = _extract_color_legacy(soup)
    gender = _extract_gender_legacy(title, soup)
    curr, orig = _extract_prices_legacy(soup)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr
    size_pairs = _extract_size_pairs_legacy(soup)
    product_size, product_size_detail = _build_size_lines_legacy(size_pairs, gender)

    info = {
        "Product Code": "No Data",
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

def parse_info_new(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    jd = _from_jsonld_product_new(soup) or {}

    title = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc  = jd.get("description") or "No Data"
    curr, orig = _extract_prices_new(soup, html)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr

    # ✅ 先确定 gender
    gender = "women" if "/women" in url.lower() else ("men" if "/men" in url.lower() else "No Data")
    # ✅ 再调用提尺码，并补齐 0
    product_size, product_size_detail = _extract_sizes_new(soup, gender)

    info = {
        "Product Code": jd.get("sku") or "No Data",
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": "No Data",
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

# ================== 统一对外：parse_info ==================
def parse_info(html: str, url: str) -> Dict[str, Any]:
    ver = _classify_stack_by_html_head(html)
    if ver == "new":
        return parse_info_new(html, url)
    return parse_info_legacy(html, url)

# ================== Selenium 基础 ==================
def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless: options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return uc.Chrome(options=options)

# —— 每次新建 driver 抓一次 & 判栈；总是会 quit，确保无残留 —— #
def _fetch_once_with_fresh_driver(url: str, wait_html: int = WAIT_PRICE_SECONDS, headless: bool = False,
                                  dump_debug: bool = True, debug_dir: str | None = None, attempt_idx: int | None = None):
    driver = get_driver(headless=headless)
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, wait_html).until(EC.presence_of_element_located((By.TAG_NAME, "html")))
        except Exception:
            pass
        html = driver.page_source or ""
        ver = _classify_stack_by_html_head(html)
        if dump_debug and debug_dir:
            short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
            fn = f"stack_{ver}_fresh_attempt{(attempt_idx or 0):02d}_{short}.html"
            p = Path(debug_dir) / fn
            _atomic_write_bytes(html.encode("utf-8", errors="ignore"), p)
        return html, ver
    finally:
        try: driver.quit()
        except Exception: pass

# ================== 处理单个 URL ==================
def process_url(url: str, conn: Connection, delay: float = DEFAULT_DELAY, headless: bool = False) -> Path | None:
    print(f"\n🌐 正在抓取: {url}")

    # === “猎取 legacy”策略：每次都用全新 driver，最多 10 次 ===
    LEGACY_HUNT_MAX = 10
    REJECT_LOG = DEBUG_DIR / "new_stack_reject_urls.txt"

    html = ""
    ver = "unknown"
    got_legacy = False

    for i in range(1, LEGACY_HUNT_MAX + 1):
        html_try, ver_try = _fetch_once_with_fresh_driver(
            url,
            wait_html=WAIT_PRICE_SECONDS,
            headless=headless,
            dump_debug=True,
            debug_dir=str(DEBUG_DIR),
            attempt_idx=i
        )
        print(f"[hunt] attempt {i}/{LEGACY_HUNT_MAX} → stack = {ver_try}")
        if ver_try == "legacy":
            html, ver = html_try, ver_try
            got_legacy = True
            break
        time.sleep(0.8)  # 轻微冷却，降低风控/AB 固化

    if not got_legacy:
        # 并发安全地追加一行
        REJECT_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(REJECT_LOG, "a", encoding="utf-8", errors="ignore") as fp:
                fp.write(_normalize_url(url) + "\n")
        except Exception:
            # 兜底：原子写（可能丢其他并发行）
            old = ""
            try:
                old = REJECT_LOG.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
            _atomic_write_bytes((old + _normalize_url(url) + "\n").encode("utf-8"), REJECT_LOG)
        print(f"🛑 连续 {LEGACY_HUNT_MAX} 次未命中 legacy，放弃：{url}\n    已记录 → {REJECT_LOG}")
        return None

    # dump 一份最终用于解析的 debug1
    _dump_debug_html(html, url, tag="debug1")
    print(f"[stack] {ver}")

    # —— 解析 —— #
    info = parse_info(html, url)

    # —— 编码获取：先查缓存（URL→Code），命中则跳过模糊匹配 —— #
    norm_url = _normalize_url(url)
    code = URL_CODE_CACHE.get(norm_url)
    if code:
        print(f"🔗 缓存命中 URL→{code}（跳过模糊匹配）")
        info["Product Code"] = code
    else:
        # 未命中 → 走模糊匹配（保持原阈值/日志）
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

    # —— 生成文件名并写入 TXT —— #
    if code:
        out_path = TXT_DIR / f"{code}.txt"
    else:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        safe_name = _safe_name(info.get("Product Name") or "BARBOUR")
        out_path = TXT_DIR / f"{safe_name}_{short}.txt"

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

    # 启动前：规范化 URL 去重（保序）
    seen = set()
    urls = []
    for u in raw_urls:
        nu = _normalize_url(u)
        if nu in seen:
            continue
        seen.add(nu)
        urls.append(u)

    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0: return

    engine_url = f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['dbname']}"
    engine = create_engine(engine_url)

    # ★ 启动阶段仅构建一次缓存（offers + products）
    with engine.begin() as conn:
        raw = get_dbapi_connection(conn)
        build_url_code_cache(raw, PRODUCTS_TABLE, OFFERS_TABLE, SITE_NAME)

    indexed = list(enumerate(urls, start=1))

    def _worker(idx_url):
        idx, u = idx_url
        print(f"[启动] [{idx}/{total}] {u}")
        try:
            with engine.begin() as conn:
                path = process_url(u, conn=conn, delay=delay, headless=headless)
            if path is None:
                # 未命中 legacy：视作失败
                return (idx, u, None, RuntimeError("no legacy after retries"))
            return (idx, u, str(path), None)
        except Exception as e:
            return (idx, u, None, e)

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hof") as ex:
        futures = [ex.submit(_worker, iu) for iu in indexed]
        for fut in as_completed(futures):
            idx, u, path, err = fut.result()
            if err is None:
                ok += 1; print(f"[完成] [{idx}/{total}] ✅ {u} -> {path}")
            else:
                fail += 1; print(f"[失败] [{idx}/{total}] ❌ {u}\n    {repr(err)}")
    print(f"\n📦 任务结束：成功 {ok}，失败 {fail}，总计 {total}")

if __name__ == "__main__":
    houseoffraser_fetch_info()
