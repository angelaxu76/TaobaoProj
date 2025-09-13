# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour 商品抓取（双通道：旧版 + 新版）
- 旧版解析：parse_info_legacy（保持你原有逻辑）
- 新版解析：parse_info_new（针对 Next/GraphQL 页，静态解析 JSON-LD + 脚本中的价签原始值 + 新版尺码/颜色）
- 对外接口不变：parse_info / process_url / houseoffraser_fetch_info
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

# ====== 项目依赖（保持不变）======
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

# ================== 小工具 ==================

import re

# 去掉 option 文本中自带的 “- Out of stock / Out of stock”等噪音
def _strip_oos_suffix(label: str) -> str:
    s = (label or "").strip()
    # 常见格式： "16- Out of stock" / "16 - Out Of Stock" / "16  Out of stock"
    s = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*Out\s*of\s*stock\s*$", "", s, flags=re.IGNORECASE)
    return s.strip(" -/")

def _build_size_lines_common(entries):
    """
    entries: [(size_norm, status)]，status ∈ {"有货","无货"}
    输出：
      Product Size:  size:状态;size:状态（保持你现有格式以兼容下游）
      Product Size Detail: size:qty:EAN（有货=3，无货=0；EAN占位）
    """
    if not entries:
        return "No Data", "No Data"

    # 同尺码多条时，“有货”优先
    by_size = {}
    for size, status in entries:
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            by_size[size] = status

    # 保持出现顺序
    ordered = [s for s, _ in entries if s in by_size]
    seen = set()
    ordered = [s for s in ordered if not (s in seen or seen.add(s))]

    EAN = "0000000000000"
    product_size = ";".join(f"{s}:{by_size[s]}" for s in ordered) or "No Data"
    product_size_detail = ";".join(
        f"{s}:{3 if by_size[s]=='有货' else 0}:{EAN}" for s in ordered
    ) or "No Data"
    return product_size, product_size_detail



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

def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _to_num(s: Optional[str]) -> Optional[float]:
    if not s: return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s.replace(",", ""))
    return float(m.group(1)) if m else None

# ================== 栈判定 & 抓取策略（保留） ==================
def _classify_stack_by_html_head(html: str) -> str:
    """返回 'legacy' / 'new' / 'unknown'，仅看 <html> 头部与早期资源特征。"""
    head = html[:8192].lower()
    if ('class="fraserspx"' in head) or ('data-recs-provider="graphql"' in head) or ('/_next/static/' in head):
        return "new"
    if ('xmlns="http://www.w3.org/1999/xhtml"' in head) or ('/wstatic/dist/' in head) or ('var datalayerdata' in head):
        return "legacy"
    return "unknown"

def _get_html_preferring_legacy(driver, url: str, tries: int = 3, wait_html: int = 8, dump_debug=False, debug_dir: str = None):
    """
    尝试优先拿 legacy；若连续命中新栈则返回最后一次 HTML。
    """
    last_html, last_ver = "", "unknown"
    for i in range(tries):
        if i > 0:
            try:
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
            except Exception:
                pass
        driver.get(url)
        try:
            WebDriverWait(driver, wait_html).until(EC.presence_of_element_located((By.TAG_NAME, "html")))
        except Exception:
            pass
        html = driver.page_source
        ver = _classify_stack_by_html_head(html)
        if dump_debug and debug_dir:
            short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
            p = Path(debug_dir) / f"stack_{ver}_attempt{i+1}_{short}.html"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf-8", errors="ignore")
        if ver == "legacy":
            return html, ver
        last_html, last_ver = html, ver
        if ver != "new":  # unknown 则不无限重试
            break
    return last_html, last_ver

# ================== 旧版解析（保持你原有逻辑，只是函数名改为 parse_info_legacy） ==================
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
    """
    旧版：select#sizeDdl > option
    返回 [(规范化尺码, '有货'|'无货'), ...]
    """
    sel = soup.find("select", id="sizeDdl")
    entries = []
    if not sel:
        return entries

    for opt in sel.find_all("option"):
        raw_label = (opt.get_text() or "").strip()
        if not raw_label or raw_label.lower().startswith("select"):
            continue

        # 判定库存：disabled/class/title 或 文本包含 out of stock
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

        # 清洗掉 “- Out of stock”等噪音，再做统一尺码清洗
        clean_label = _strip_oos_suffix(raw_label)
        size_norm = _norm_size(clean_label)
        if not size_norm:
            continue

        entries.append((size_norm, status))
    return entries

def _build_size_lines_legacy(pairs: List[Tuple[str, str]]) -> Tuple[str, str]:
    by_size: Dict[str, str] = {}
    for size, status in pairs:
        prev = by_size.get(size)
        if prev is None or (prev == "无货" and status == "有货"): by_size[size] = status
    def _key(k: str):
        m = re.fullmatch(r"\d{1,3}", k)
        return (0, int(k)) if m else (1, k)
    ordered = sorted(by_size.keys(), key=_key)
    ps = ";".join(f"{k}:{by_size[k]}" for k in ordered) or "No Data"
    EAN = "0000000000000"
    psd = ";".join(f"{k}:{3 if by_size[k]=='有货' else 0}:{EAN}" for k in ordered) or "No Data"
    return ps, psd


def _extract_color_new(soup: BeautifulSoup, url: Optional[str]) -> str:
    """
    新版颜色：优先用 URL/页面中的 #colcode 精确匹配 JSON-LD offers → itemOffered.color；
    兜底：脚本文本正则匹配 sku→color；再退回图片 alt；最后退回 og:image:alt。
    """
    import re as _re, json as _json

    html_text = soup.decode()

    # 1) colcode 来源：URL → canonical → og:url
    colcode = None
    if url:
        m = _re.search(r"colcode=(\d{6,})", url)
        if m: colcode = m.group(1)
    if not colcode:
        cano = soup.find("link", attrs={"rel": "canonical"})
        href = (cano.get("href") if cano else "") or ""
        m = _re.search(r"colcode=(\d{6,})", href)
        if m: colcode = m.group(1)
    if not colcode:
        ogu = soup.find("meta", attrs={"property": "og:url"})
        href = (ogu.get("content") if ogu else "") or ""
        m = _re.search(r"colcode=(\d{6,})", href)
        if m: colcode = m.group(1)

    # 没有 colcode 很难精准，直接退回 og:image:alt
    def _fallback_og_alt() -> str:
        m = soup.find("meta", attrs={"property": "og:image:alt"})
        if m and m.get("content"):
            return m["content"].split(" - ")[0].strip()
        return "No Data"

    if not colcode:
        return _fallback_og_alt()

    # 2) JSON-LD：按 sku/gtin* 精确匹配，取 itemOffered.color
    try:
        for sc in soup.find_all("script", {"type": "application/ld+json"}):
            txt = sc.string or sc.get_text() or ""
            if not txt.strip():
                continue
            try:
                data = _json.loads(txt)
            except Exception:
                continue

            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue

                # 可能是直接 Product，也可能在 @graph 里
                products = []
                if node.get("@type") == "Product":
                    products.append(node)
                if isinstance(node.get("@graph"), list):
                    products += [g for g in node["@graph"] if isinstance(g, dict) and g.get("@type") == "Product"]

                for prod in products:
                    offers = prod.get("offers")
                    offer_items = []
                    if isinstance(offers, dict):
                        if isinstance(offers.get("offers"), list):
                            offer_items += offers["offers"]
                        else:
                            offer_items.append(offers)
                    elif isinstance(offers, list):
                        offer_items += offers

                    for off in offer_items:
                        if not isinstance(off, dict):
                            continue
                        sku = str(off.get("sku") or "").strip()
                        io  = off.get("itemOffered") or {}
                        gtins = []
                        if isinstance(io, dict):
                            for k in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14"):
                                v = io.get(k)
                                if v: gtins.append(str(v).strip())
                        if colcode == sku or colcode in gtins:
                            color = (io.get("color") if isinstance(io, dict) else None) or off.get("color")
                            if isinstance(color, str) and color.strip():
                                return color.strip()
    except Exception:
        pass

    # 3) 兜底：脚本文本里按 "sku":"{colcode}" … "color":"XXX" 搜
    try:
        pat = _re.compile(
            r'"sku"\s*:\s*"' + _re.escape(colcode) + r'"\s*,[^}]*?"color"\s*:\s*"([^"]+)"',
            _re.S | _re.I
        )
        m = pat.search(html_text)
        if m:
            return m.group(1).strip()
    except Exception:
        pass

    # 4) 再兜底：图片路径里含 colcode 的 img.alt
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if colcode in src:
            alt = (img.get("alt") or "").strip()
            if alt:
                return alt.split(" - ")[0].strip()

    # 5) 最后退回 og:image:alt
    return _fallback_og_alt()



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
    product_size, product_size_detail = _build_size_lines_legacy(size_pairs)
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

# ================== 新版解析（Next/GraphQL 页，静态解析） ==================
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
            colors: set[str] = set()
            avail_map: Dict[str, str] = {}
            curr_prices: List[float] = []

            offers = obj.get("offers")
            if isinstance(offers, dict):
                nested = offers.get("offers") or []
                for off in nested:
                    p = off.get("price")
                    if p:
                        try: curr_prices.append(float(p))
                        except: pass
                    io = off.get("itemOffered") or {}
                    col = io.get("color") if isinstance(io, dict) else None
                    if col:
                        colors.add(col)
                        avail = off.get("availability") or ""
                        avail_map[col] = "有货" if "InStock" in avail else ("无货" if avail else "No Data")
                if not curr_prices and offers.get("lowPrice"):
                    try: curr_prices.append(float(offers["lowPrice"]))
                    except: pass

            out["current_price_guess"] = (min(curr_prices) if curr_prices else None)
            out["colors_all"] = sorted(colors)
            out["availability_by_color"] = avail_map
            return out
    return out

def _extract_selected_color_new(soup: BeautifulSoup) -> Optional[str]:
    # og:image:alt 一般是 "Black - Brand - Product - 1"
    for m in soup.find_all("meta", {"property": "og:image:alt"}):
        cont = (m.get("content") or "").strip()
        if not cont:
            continue
        first = cont.split("-")[0].strip()
        if first and first.lower() not in ("house of fraser",):
            return first
    # 退回 title 里的括号
    if soup.title:
        mt = re.search(r"\(([^)]+)\)", soup.title.get_text())
        if mt:
            return mt.group(1).strip()
    return None

def _extract_prices_new(soup: BeautifulSoup, html_text: str) -> Tuple[Optional[float], Optional[float]]:
    """
    新版页面价格来源（无需跑JS）：
    - DOM 属性 data-testvalue="17900"/"21900" → £179.00 / £219.00
    - data-testid="ticket-price" → 原价（若存在）
    - 兜底：脚本文本里的 RefPriceRaw / RefPrice
    """
    nums: List[float] = []

    # data-testvalue
    for tag in soup.find_all(attrs={"data-testvalue": True}):
        v = tag.get("data-testvalue")
        try:
            n = float(v) / 100.0
            nums.append(n)
        except Exception:
            pass

    # ticket-price（原价）
    t = soup.find(attrs={"data-testid": "ticket-price"})
    if t:
        val = _to_num(t.get_text())
        if val is not None:
            nums.append(val)

    # 脚本文本兜底（RefPriceRaw / SellPriceRaw）
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
    return nums[0], nums[-1]  # 最小当现价，最大当原价

def _extract_sizes_new(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    新版：<option data-testid="drop-down-option" value="...">8 (XS)</option>
    disabled / aria-disabled='true' → 无货
    """
    entries = []
    for opt in soup.find_all("option", attrs={"data-testid": "drop-down-option"}):
        val = (opt.get("value") or "").strip()
        if not val:  # "Select a size"
            continue

        raw_label = (opt.get_text() or "").strip()
        clean_label = _strip_oos_suffix(raw_label)
        size_norm = _norm_size(clean_label)
        if not size_norm:
            continue

        oos = opt.has_attr("disabled") or (opt.get("aria-disabled") == "true") \
              or "out of stock" in raw_label.lower()
        status = "无货" if oos else "有货"
        entries.append((size_norm, status))

    if not entries:
        return "No Data", "No Data"
    return _build_size_lines_common(entries)

def parse_info_new(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    jd = _from_jsonld_product_new(soup) or {}

    title = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc  = jd.get("description") or "No Data"
    curr, orig = _extract_prices_new(soup, html)
    if curr is None and orig is not None: curr = orig
    if orig is None and curr is not None: orig = curr


    all_colors = (jd.get("colors_all") or []) if isinstance(jd, dict) else []
    color = _extract_color_new(soup, url)  # 精确：用 #colcode 命中 JSON-LD offers → itemOffered.color
    if not color or color == "No Data":
        sel_color = _extract_selected_color_new(soup)  # 退回 og:image:alt 的前缀/或 title 中括号
        color = sel_color or (";".join(all_colors) if all_colors else "No Data")

    product_size, product_size_detail = _extract_sizes_new(soup)

    gender = "women" if "/women" in url.lower() else ("men" if "/men" in url.lower() else "No Data")

    info = {
        "Product Code": jd.get("sku") or "No Data",
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": f"{orig:.2f}" if isinstance(orig, (int, float)) else "No Data",      # 原价
        "Adjusted Price": f"{curr:.2f}" if isinstance(curr, (int, float)) else "No Data",     # 现价
        "Product Material": "No Data",
        "Style Category": "casual wear",
        "Feature": "No Data",
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Source URL": url,
        "Site Name": SITE_NAME,

        # 调试辅助（可忽略）
        "_debug_colors_all": all_colors,
        "_debug_availability_by_color": jd.get("availability_by_color") or {},
    }
    return info

# ================== 统一对外：parse_info（仅作为分发器；签名不变） ==================
def parse_info(html: str, url: str) -> Dict[str, Any]:
    ver = _classify_stack_by_html_head(html)
    if ver == "new":
        return parse_info_new(html, url)
    # legacy 或 unknown 都走旧版逻辑（更兼容）
    return parse_info_legacy(html, url)

# ================== Selenium & 抓取流程（函数名/入参保持不变） ==================
def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless: options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return uc.Chrome(options=options)

def process_url(url: str, conn: Connection, delay: float = DEFAULT_DELAY, headless: bool = False) -> Path:
    print(f"\n🌐 正在抓取: {url}")
    driver = get_driver(headless=headless)
    try:
        # 取 HTML（保留“尽量拿旧版”的策略；即便是新版也能解析）
        html, ver = _get_html_preferring_legacy(
            driver, url,
            tries=3,
            wait_html=WAIT_PRICE_SECONDS,
            dump_debug=True,
            debug_dir=str(TXT_DIR / "_debug")
        )
        print(f"[stack] {ver}")
        _dump_debug_html(html, url, tag="debug1")
    finally:
        try: driver.quit()
        except Exception: pass

    # 解析 & 匹配（保持不变）
    info = parse_info(html, url)

    raw_conn = get_dbapi_connection(conn)
    title = info.get("Product Name") or ""
    color = info.get("Product Color") or ""
    results = match_product(
        raw_conn,
        scraped_title=title, scraped_color=color,
        table=PRODUCTS_TABLE,
        name_weight=0.72, color_weight=0.18, type_weight=0.10,
        topk=5, recall_limit=2000, min_name=0.92, min_color=0.85,
        require_color_exact=False, require_type=False,
    )
    code = choose_best(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
    if not code and results:
        st = results[0].get("type_scraped")
        if st:
            for r in results:
                if r.get("type_db") == st:
                    code = r["product_code"]; print(f"🎯 tie-break by type → {code}"); break

    print("🔎 match debug")
    print(f"  raw_title: {title}")
    print(f"  raw_color: {color}")
    if results: print(f"  cleaned : {results[0].get('title_clean')}")
    txt, why = explain_results(results, min_score=MIN_SCORE, min_lead=MIN_LEAD)
    print(txt)
    if code: print(f"  ⇒ ✅ choose_best = {code}")
    else:    print(f"  ⇒ ❌ no match ({why})")
    if not code and results:
        print("🧪 top:", " | ".join(f"{r['product_code']}[{r['score']:.3f}]" for r in results[:3]))

    # 命名与写入（始终覆盖）
    if code:
        info["Product Code"] = code
        out_name = f"{code}.txt"
    else:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        out_name = f"{_safe_name(title)}_{short}.txt"

    out_path = TXT_DIR / out_name
    with _WRITTEN_LOCK:
        _WRITTEN.add(out_name)
    payload = _kv_txt_bytes(info)
    ok = _atomic_write_bytes(payload, out_path)
    if ok:
        print(f"✅ 写入: {out_path} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")
    return out_path

def houseoffraser_fetch_info(max_workers: int = MAX_WORKERS_DEFAULT, delay: float = DEFAULT_DELAY, headless: bool = False):
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return
    urls = [line.strip() for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")]
    total = len(urls)
    print(f"📄 共 {total} 个商品页面待解析...（并发 {max_workers}）")
    if total == 0: return

    engine_url = f"postgresql+psycopg2://{PG['user']}:{PG['password']}@{PG['host']}:{PG['port']}/{PG['dbname']}"
    engine = create_engine(engine_url)

    indexed = list(enumerate(urls, start=1))

    def _worker(idx_url):
        idx, u = idx_url
        print(f"[启动] [{idx}/{total}] {u}")
        try:
            with engine.begin() as conn:
                path = process_url(u, conn=conn, delay=delay, headless=headless)
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
