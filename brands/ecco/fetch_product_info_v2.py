# -*- coding: utf-8 -*-
"""
ECCO UK (Next.js) 抓取 v2
修复：v1 中 JSON-LD 缓存旧折扣价导致无折扣商品被误标 Adjusted Price 的 bug。

核心改动（相比 v1）：
  1. extract_prices() 重写：DOM 优先，只有页面同时存在「原价 + 折后价」两个元素
     时才认为有折扣；JSON-LD 降为 DOM 全部失败时的最后兜底。
  2. 新增 SELENIUM_FIRST 选项：True 时对所有 URL 直接用 Selenium 抓
     (ECCO 是 Next.js 站，浏览器渲染的价格最准确)。
  3. 其余逻辑与 v1 完全一致。
"""
import time
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from config import ECCO, SIZE_RANGE_CONFIG
import requests
from bs4 import BeautifulSoup
import json
import re
import demjson3

from common.ingest.txt_writer import format_txt

# ===== 路径配置 =====
LINKS_FILE = ECCO["LINKS_FILE"]
TXT_DIR    = ECCO["TXT_DIR"]
DEBUG_DIR  = ECCO["BASE"] / "publication" / "debug_pages"

DEBUG_SAVE_HTML  = True
REQUEST_TIMEOUT  = 20
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9"
}

ENABLE_SELENIUM    = True
SELENIUM_FIRST     = True   # ★ True = 对所有 URL 直接走 Selenium（Next.js 站推荐）
                             #   False = requests 优先，失败才回退 Selenium（v1 行为）
CHROMEDRIVER_PATH  = r"D:/Software/chromedriver-win64/chromedriver.exe"
MAX_WORKERS        = 1


# ============ 工具函数（与 v1 相同）============

def supplement_ecco_sizes(size_map, size_detail, gender):
    brand_cfg = SIZE_RANGE_CONFIG.get("ecco", {})
    key = {"men": "男款", "women": "女款", "kids": "童款"}.get(gender)
    if not key:
        return size_map, size_detail
    for eu in brand_cfg.get(key, []):
        if eu not in size_detail:
            size_map[eu] = "无货"
            size_detail[eu] = {"stock_count": 0, "ean": "0000000000000"}
    return size_map, size_detail


def parse_ecco_sizes_and_stock(html):
    def _unescape(s):
        return s.replace('\\"', '"').replace('\\\\', '\\')

    rows = []

    # A) variants 主渠道
    m_variants_plain = re.search(r'"variants"\s*:\s*(\[[\s\S]*?\])', html)
    m_variants_esc   = re.search(r'\\"variants\\":\s*(\[[\s\S]*?\])', html)
    block_variants = None
    if m_variants_plain:
        block_variants = m_variants_plain.group(1)
    elif m_variants_esc:
        block_variants = _unescape(m_variants_esc.group(1))

    if block_variants:
        try:
            variants = demjson3.decode(_unescape(block_variants))
            for v in variants if isinstance(variants, list) else []:
                sku = str(v.get("sku") or "")
                size_eu = size_uk = None
                for a in v.get("attributesRaw", []) or []:
                    if a.get("name") == "Size":    size_eu = a.get("value")
                    if a.get("name") == "Size_UK": size_uk = a.get("value")
                qty, on = 0, False
                for c in (v.get("availability", {}) or {}).get("channels", {}).get("results", []) or []:
                    if (c.get("channel", {}) or {}).get("key") == "GB-web":
                        av = c.get("availability", {}) or {}
                        try:
                            qty = int(av.get("availableQuantity") or 0)
                        except Exception:
                            qty = 0
                        on = bool(av.get("isOnStock"))
                        break
                if size_eu:
                    rows.append({
                        "sku": sku, "size_eu": str(size_eu),
                        "size_uk": str(size_uk) if size_uk is not None else "",
                        "available_qty": qty, "has_stock": on
                    })
        except Exception:
            pass

    # B) relatedProduct.variants 兜底回填
    m_rel_plain = re.search(r'"relatedProduct"\s*:\s*\{\s*"variants"\s*:\s*(\[[\s\S]*?\])', html)
    m_rel_esc   = re.search(r'\\"relatedProduct\\":\s*\{\s*\\"variants\\":\s*(\[[\s\S]*?\])', html)
    block_rel = None
    if m_rel_plain:
        block_rel = m_rel_plain.group(1)
    elif m_rel_esc:
        block_rel = _unescape(m_rel_esc.group(1))

    if block_rel:
        try:
            rel = demjson3.decode(_unescape(block_rel))
            by_key = {(r["sku"], r["size_eu"]): r for r in rows if r.get("sku") and r.get("size_eu")}
            for v in rel if isinstance(rel, list) else []:
                sku = str(v.get("sku") or "")
                eu  = str(v.get("size") or v.get("eu") or v.get("label") or "")
                if not sku or not eu:
                    continue
                uk  = str(v.get("sizeUK") or v.get("uk") or "")
                try:
                    qty = int(v.get("availableQuantity") or 0)
                except Exception:
                    qty = 0
                has = v.get("hasStock")
                key = (sku, eu)
                if key in by_key:
                    r = by_key[key]
                    if not r.get("size_uk") and uk: r["size_uk"] = uk
                    if (r.get("available_qty") is None) or (r.get("available_qty") == 0):
                        r["available_qty"] = qty
                        r["has_stock"] = bool(has) if has is not None else (qty > 0)
                else:
                    rows.append({
                        "sku": sku, "size_eu": eu, "size_uk": uk,
                        "available_qty": qty,
                        "has_stock": bool(has) if has is not None else (qty > 0)
                    })
        except Exception:
            pass

    # C) 清洗 & 排序
    def _eu_key(s):
        try: return int(str(s).split("-")[0])
        except Exception: return 999

    cleaned, seen = [], set()
    for r in rows:
        eu, sku = r.get("size_eu"), r.get("sku")
        if not eu or not sku:
            continue
        key = (sku, eu)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(r)
    cleaned.sort(key=lambda x: _eu_key(x.get("size_eu", "")))
    return cleaned


def build_size_maps_jingya(rows):
    def in_stock(r):
        q = r.get("available_qty")
        has = r.get("has_stock")
        if has is True: return True
        try: return int(q) > 0
        except Exception: return False

    def eu_key(s):
        try: return int(str(s).split("-")[0])
        except Exception: return 999

    size_map, size_detail, seen = {}, {}, set()
    for r in sorted(rows, key=lambda x: eu_key(x.get("size_eu", ""))):
        eu = str(r.get("size_eu") or "").strip()
        if not eu or eu in seen:
            continue
        seen.add(eu)
        ok = in_stock(r)
        sku = str(r.get("sku") or "").strip()
        ean = sku if (len(sku) == 13 and sku.isdigit()) else "0000000000000"
        size_map[eu]    = "有货" if ok else "无货"
        size_detail[eu] = {"stock_count": 3 if ok else 0, "ean": ean}
    return size_map, size_detail


def extract_sizes(html, soup):
    results = []
    size_div = soup.find("div", class_="size-picker__rows")
    if size_div:
        for btn in size_div.find_all("button"):
            label = re.sub(r"\s+", " ", (btn.get_text(" ", strip=True) or "")).strip()
            if not label:
                continue
            eu_m = re.search(r"\b(\d{2})\b", label)
            eu_size = eu_m.group(1) if eu_m else label
            classes = " ".join(btn.get("class", []))
            soldout = any(k in classes.lower() for k in ("soldout", "disabled", "unavailable"))
            results.append(f"{eu_size}:{'无货' if soldout else '有货'}")
        if results:
            return results
    for s in soup.find_all("script"):
        txt = s.string or ""
        if not txt:
            continue
        if ("size" in txt.lower() or "variant" in txt.lower()) and \
           ("stock" in txt.lower() or "availability" in txt.lower()):
            pairs = re.findall(
                r'("?(?:eu|size|label)"?\s*:\s*"?(\d{2})"?).*?'
                r'("?(?:inStock|available|availability)"?\s*:\s*'
                r'(?:true|false|"?(?:InStock|OutOfStock)"?))',
                txt, flags=re.I | re.S
            )
            added = set()
            for p in pairs:
                eu = p[1]
                avail_part = p[2].lower()
                soldout = ("false" in avail_part) or ("outofstock" in avail_part)
                key = f"{eu}:{'无货' if soldout else '有货'}"
                if key not in added:
                    results.append(key)
                    added.add(key)
            if results:
                return results
    return results


# ============ ★ 核心修复：价格提取 v2 ============

def extract_prices(html: str, soup: BeautifulSoup):
    """
    返回 (Price, AdjustedPrice)
      - 无折扣 → (full_price, 0.0)
      - 有折扣 → (orig_price, sale_price)

    优先级：
      1. 老站 onProductPageInit（不变）
      2. DOM 双价格元素（★ 新逻辑：必须同时存在「原价 + 折后价」才认定打折）
      3. DOM 单价格元素（只有一个价格 = 正价，AdjustedPrice = 0）
      4. JSON-LD 最后兜底（仅在 DOM 完全失败时）
    """

    def _money(text: str) -> float:
        if not text:
            return 0.0
        m = re.search(r'(\d+(?:\.\d+)?)', (text or "").replace(",", ""))
        return float(m.group(1)) if m else 0.0

    # ── 1) 老站 onProductPageInit ──────────────────────────────────────────
    try:
        m = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if m:
            data = json.loads(m.group(1).replace("&quot;", '"'))
            p  = float(data.get("Price", 0) or 0)
            ap = float(data.get("AdjustedPrice", 0) or 0)
            return p, ap
    except Exception:
        pass

    # ── 2) DOM：查找「明确的折后价元素」──────────────────────────────────────
    # 打折时 ECCO 页面会同时渲染一个独立的 sale/discount 价格元素；
    # 不打折时该元素不存在，只留 RecommendedPrice（或 RegularPrice）。
    sale_elem = (
        soup.find(attrs={"data-testid": "SalePrice"}) or
        soup.find(attrs={"data-testid": "DiscountedPrice"}) or
        soup.find(attrs={"data-testid": "FinalPrice"}) or
        soup.select_one("[class*='sale-price']") or
        soup.select_one("[class*='discount-price']") or
        soup.select_one("[class*='SalePrice']")
    )

    # 「原价 / 建议零售价」元素（打折时显示划线，不打折时就是售价）
    rrp_elem = (
        soup.find(attrs={"data-testid": "RecommendedPrice"}) or
        soup.find(attrs={"data-testid": "RegularPrice"}) or
        soup.find(attrs={"data-testid": "OriginalPrice"})
    )

    # 通用「当前售价」元素
    current_elem = (
        soup.find(attrs={"data-testid": "CurrentPrice"}) or
        soup.find(attrs={"data-testid": "ProductPrice"}) or
        soup.select_one("p.product-price") or
        soup.select_one("[class*='ProductPrice']") or
        soup.select_one("[class*='product-price']")
    )

    sale_val    = _money(sale_elem.get_text(" ", strip=True))    if sale_elem    else 0.0
    rrp_val     = _money(rrp_elem.get_text(" ", strip=True))     if rrp_elem     else 0.0
    current_val = _money(current_elem.get_text(" ", strip=True)) if current_elem else 0.0

    # Case A：明确存在独立折后价 + 原价 → 有折扣
    if sale_val > 0 and rrp_val > 0 and rrp_val > sale_val:
        return rrp_val, sale_val

    # Case B：只有「当前售价」+ 「原价」，且两者相同 → 无折扣
    if rrp_val > 0 and current_val > 0 and rrp_val == current_val:
        return rrp_val, 0.0

    # Case C：只有单一价格元素（最常见的不打折情况）
    if rrp_val > 0 and sale_val == 0:
        return rrp_val, 0.0
    if current_val > 0 and sale_val == 0:
        return current_val, 0.0

    # ── 3) JSON-LD 最后兜底（DOM 完全取不到时才用）────────────────────────────
    # 注意：JSON-LD 价格可能有缓存，只返回 (price, 0.0)，不推断折扣。
    try:
        for s in soup.find_all("script", {"type": "application/ld+json"}):
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                offers = item.get("offers")
                if isinstance(offers, dict) and "price" in offers:
                    p = float(str(offers.get("price", "0")).replace(",", "") or 0)
                    if p > 0:
                        return p, 0.0
    except Exception:
        pass

    return 0.0, 0.0


# ============ 其他解析函数（与 v1 相同）============

def extract_code(soup, url=""):
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                for k in ("sku", "mpn", "productID", "productId"):
                    v = str(item.get(k, "")).strip()
                    if v:
                        m = re.search(r"(\d{6})\D*(\d{5})", v)
                        if m: return f"{m.group(1)}{m.group(2)}"
                        m2 = re.search(r"\b(\d{10,12})\b", v)
                        if m2: return m2.group(1)
        except Exception:
            pass
    node = soup.find("div", class_="product_info__product-number")
    if node:
        t = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        m = re.search(r"(\d{6})\D+(\d{5})", t)
        if m: return f"{m.group(1)}{m.group(2)}"
        m2 = re.search(r"\b(\d{10,12})\b", t)
        if m2: return m2.group(1)
    href = ""
    for meta_args in [{"property": "og:url"}, {"name": "twitter:url"}]:
        tag = soup.find("meta", attrs=meta_args)
        if tag and tag.get("content"):
            href = tag["content"]
            break
    if not href: href = url or ""
    m = re.search(r"/(\d{6})/(\d{5})(?:[/?#]|$)", href)
    if m: return f"{m.group(1)}{m.group(2)}"
    m2 = re.search(r"/product/(\d{10,12})(?:[/?#]|$)", href)
    if m2: return m2.group(1)
    text = soup.get_text(" ", strip=True)
    m3 = re.search(r"\b(\d{6})\D{0,3}(\d{5})\b", text)
    if m3: return f"{m3.group(1)}{m3.group(2)}"
    m4 = re.search(r"\b(\d{10,12})\b", text)
    if m4: return m4.group(1)
    raise RuntimeError("Product Code not found")


def extract_names(soup):
    h1 = soup.select_one('[data-testid="product-card-titleandprice"] h1')
    marketing = model = ""
    if h1:
        p = h1.find("p")
        marketing = re.sub(r"\s+", " ", (p.get_text(" ", strip=True) if p else "")).strip()
        tails = h1.find_all(string=True, recursive=False)
        model = re.sub(r"\s+", " ", tails[0]).strip() if tails else ""
    og_title = ""
    tag = soup.find("meta", attrs={"property": "og:title"})
    if tag and tag.get("content"):
        og_title = re.sub(r"\s+", " ", tag["content"]).strip()
    if not (marketing or model) and og_title:
        left = og_title.split(" | ", 1)[0]
        left = re.sub(r"\bECCO\b|\bECCO®\b", "", left, flags=re.I)
        marketing = re.sub(r"\s+", " ", left).strip()
    merged = " | ".join([x for x in [marketing, model] if x]) or og_title
    return marketing, model, merged


def extract_description(soup):
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                desc = item.get("description", "")
                if desc:
                    text = re.sub(r"<[^>]+>", " ", desc)
                    return re.sub(r"\s+", " ", unescape(text)).strip()
        except Exception:
            pass
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(tag["content"]))).strip()
    node = soup.select_one("div.product-description")
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def extract_color(soup):
    node = soup.select_one("span.product_info__color--selected")
    if node:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    tag = soup.find("meta", attrs={"property": "og:title"})
    og_title = tag["content"] if (tag and tag.get("content")) else ""
    if " | " in og_title:
        return re.sub(r"\s+", " ", og_title.split(" | ", 1)[1]).strip()
    return "No Data"


MATERIAL_WORDS = [
    "Leather", "Nubuck", "Suede", "Textile", "Mesh", "Canvas",
    "Rubber", "GORE-TEX", "Gore-Tex", "GORETEX", "Synthetic", "PU", "TPU", "EVA", "Wool", "Neoprene"
]

def parse_gender(*texts):
    t = " ".join([x or "" for x in texts]).lower()
    if "women" in t or "ladies" in t: return "women"
    if "men" in t: return "men"
    if any(k in t for k in ("kid", "junior", "youth")): return "kids"
    return ""

def parse_materials(*texts):
    joined = " | ".join([x or "" for x in texts])
    hits, seen, out = [], set(), []
    for w in MATERIAL_WORDS:
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", joined, re.I):
            hits.append(w if w.isupper() else w.title())
    for x in hits:
        xl = x.lower()
        if xl in seen: continue
        seen.add(xl); out.append(x)
    return ", ".join(out) if out else "No Data"


# ============ HTML 抓取 ============

def ensure_dirs(*paths):
    for p in paths: p.mkdir(parents=True, exist_ok=True)

def is_url(s): return str(s).startswith("http://") or str(s).startswith("https://")

def guess_code_from_url(url):
    m = re.search(r"/(\d{6})/(\d{5})(?:[/?#]|$)", url or "")
    if m: return f"{m.group(1)}{m.group(2)}"
    m2 = re.search(r"/product/(\d{10,12})(?:[/?#]|$)", url or "")
    if m2: return m2.group(1)
    return hashlib.md5((url or "").encode("utf-8")).hexdigest()[:10]

def save_debug_html(url, html, tag="loaded"):
    if not DEBUG_SAVE_HTML: return
    ensure_dirs(DEBUG_DIR)
    code_hint = guess_code_from_url(url)
    ts = time.strftime("%Y%m%d-%H%M%S")
    (DEBUG_DIR / f"{ts}_{tag}_{code_hint}.html").write_text(html or "", encoding="utf-8", errors="ignore")

def fetch_html(url_or_file):
    if not is_url(url_or_file):
        return Path(url_or_file).read_text(encoding="utf-8", errors="ignore")
    r = requests.get(url_or_file, headers=HDRS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


_selenium_driver = None

def get_driver():
    global _selenium_driver
    if _selenium_driver is not None:
        return _selenium_driver
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    _selenium_driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    return _selenium_driver

def fetch_html_selenium(url):
    d = get_driver()
    d.get(url)
    time.sleep(1.5)
    return d.page_source


# ============ 主流程 ============

def process_one(url: str, idx: int, total: int):
    try:
        print(f"🔍 ({idx}/{total}) {url}")

        # ── HTML 获取 ─────────────────────────────────────────────────────────
        if not is_url(url):
            html = fetch_html(url)
            tag = "local"
        elif ENABLE_SELENIUM and SELENIUM_FIRST:
            # ★ SELENIUM_FIRST = True：直接用浏览器渲染，价格最准
            html = fetch_html_selenium(url)
            tag  = "sel"
        else:
            # requests 优先，按需回退
            html = fetch_html(url)
            tag  = "req"

        if DEBUG_SAVE_HTML:
            save_debug_html(url, html, f"loaded_{tag}")
        soup = BeautifulSoup(html, "html.parser")

        # requests 模式：JSON-LD / og:title 都没有时才 Selenium 回退
        if tag == "req" and ENABLE_SELENIUM:
            no_jsonld  = not soup.find("script", {"type": "application/ld+json"})
            no_ogtitle = not soup.find("meta", attrs={"property": "og:title"})
            if no_jsonld and no_ogtitle:
                html = fetch_html_selenium(url)
                if DEBUG_SAVE_HTML:
                    save_debug_html(url, html, "loaded_sel_fb")
                soup = BeautifulSoup(html, "html.parser")

        # ── 编码 / 名称 / 描述 / 颜色 ─────────────────────────────────────────
        product_code = extract_code(soup, url=url)
        marketing, model, merged_name = extract_names(soup)
        product_name = merged_name or "No Data"
        description  = extract_description(soup)
        color_name   = extract_color(soup)

        # ── 性别 / 材质 ───────────────────────────────────────────────────────
        gender_from_title = parse_gender(marketing, model, product_name)
        material          = parse_materials(marketing, model, product_name, description) or "No Data"

        # ── 尺码 + 库存 ───────────────────────────────────────────────────────
        rows = parse_ecco_sizes_and_stock(html)
        size_map, size_detail = build_size_maps_jingya(rows)
        if not size_map:
            for token in extract_sizes(html, soup):
                if ":" not in token: continue
                eu, flag = token.split(":", 1)
                eu = eu.strip()
                has = "无货" not in flag
                size_map[eu]    = "有货" if has else "无货"
                size_detail[eu] = {"stock_count": 3 if has else 0, "ean": "0000000000000"}

        # 尺码辅助判断性别
        eu_sizes_arr = [k for k in size_map if k.isdigit()]
        gender_by_size = ""
        if any(int(x) < 35 for x in eu_sizes_arr if x.isdigit()):
            gender_by_size = "kids"
        elif any(x in ("45", "46") for x in eu_sizes_arr):
            gender_by_size = "men"
        elif any(x in ("35", "36") for x in eu_sizes_arr):
            gender_by_size = "women"

        gender = gender_from_title or gender_by_size or "unisex"
        size_map, size_detail = supplement_ecco_sizes(size_map, size_detail, gender)

        # ── ★ 价格（v2 修复核心）─────────────────────────────────────────────
        price, adjusted = extract_prices(html, soup)

        # 日志：方便确认价格来源
        if adjusted > 0:
            print(f"   💰 {price} → 折后 {adjusted}")
        else:
            print(f"   💰 正价 {price}")

        # ── 要点（Features）──────────────────────────────────────────────────
        li_texts = [
            re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
            for li in soup.select(
                "div.about-this-product__container div.product-description-list ul li"
            )
            if li.get_text(strip=True)
        ]
        feature = " | ".join(li_texts)

        # ── 写文件 ────────────────────────────────────────────────────────────
        ensure_dirs(TXT_DIR)
        out_path = TXT_DIR / f"{product_code}.txt"
        info = {
            "Product Code":        product_code,
            "Product Name":        product_name,
            "Product Description": description,
            "Product Gender":      gender,
            "Product Color":       color_name,
            "Product Price":       price,
            "Adjusted Price":      adjusted,
            "Product Material":    material,
            "SizeMap":             size_map,
            "SizeDetail":          size_detail,
            "Feature":             feature,
            "Source URL":          url
        }
        format_txt(info, out_path, brand="clarks_jingya")
        print(f"✅ 写入: {out_path.name}")

    except Exception as e:
        print(f"❌ 失败: {url} -> {e}")
        try:
            err_html = html if "html" in locals() else ""
        except Exception:
            err_html = ""
        if DEBUG_SAVE_HTML and err_html:
            save_debug_html(url, err_html, "error")
        try:
            ensure_dirs(TXT_DIR)
            code_hint = guess_code_from_url(url)
            out_path  = TXT_DIR / f"{code_hint}.txt"
            info = {
                "Product Code":        code_hint,
                "Product Name":        "No Data",
                "Product Description": "",
                "Product Gender":      "unisex",
                "Product Color":       "No Data",
                "Product Price":       0.0,
                "Adjusted Price":      0.0,
                "Product Material":    "No Data",
                "SizeMap":             {},
                "SizeDetail":          {},
                "Feature":             "",
                "Source URL":          url
            }
            format_txt(info, out_path, brand="clarks_jingya")
            print(f"⚠️ 已写占位: {out_path.name}")
        except Exception:
            pass


def ecco_fetch_info(links_file=None, max_workers: int = MAX_WORKERS):
    links_path = Path(links_file) if links_file else LINKS_FILE
    ensure_dirs(TXT_DIR, DEBUG_DIR)
    if not links_path.exists():
        raise FileNotFoundError(f"链接文件不存在: {links_path}")

    urls = [u.strip() for u in links_path.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    print(f"📦 共 {total} 条，线程 {max_workers}，Selenium: {ENABLE_SELENIUM}，SELENIUM_FIRST: {SELENIUM_FIRST}")
    if total == 0:
        print("⚠️ 链接文件为空，直接退出。")
        return

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(process_one, url, i + 1, total) for i, url in enumerate(urls)]
        for _ in as_completed(futures):
            pass

    if ENABLE_SELENIUM:
        try:
            get_driver().quit()
        except Exception:
            pass

    print("✅ 完成")


if __name__ == "__main__":
    ecco_fetch_info()
