# -*- coding: utf-8 -*-
"""
ECCO UK (Next.js) 全新抓取 → Clarks Jingya 格式
- 输入: product_links.txt（每行一个 URL；也支持本地 .html 便于调试）
- 输出: /TXT/{product_code}.txt  和  可选 /debug_pages/*.html
- 字段: Code / Name / Description / Gender / Color / Price / Adjusted Price / Material / Size / Feature / Source URL
"""
import time
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from config import ECCO, SIZE_RANGE_CONFIG, GLOBAL_CHROMEDRIVER_PATH, DEFAULT_STOCK_COUNT
import requests
from bs4 import BeautifulSoup
import json

# ===== 你本地已有的写入器：保持与现有工程兼容 =====
from common.ingest.txt_writer import format_txt  # format_txt(info, filepath, brand="clarks")

# ===== 路径配置（按需改）=====
LINKS_FILE = ECCO["LINKS_FILE"]
TXT_DIR    = ECCO["TXT_DIR"]
DEBUG_DIR  = ECCO["BASE"] / "publication" / "debug_pages"


# 是否保存 HTML 调试页
DEBUG_SAVE_HTML = True

# requests
REQUEST_TIMEOUT = 20
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9"
}

# 可选：Selenium 回退（动态库存/变体更稳）
ENABLE_SELENIUM = True
CHROMEDRIVER_PATH = GLOBAL_CHROMEDRIVER_PATH

# 线程
MAX_WORKERS = 1

# ============ 小工具 ============


import re
import demjson3  # 确保已安装: pip install demjson3


def supplement_ecco_sizes(size_map: dict, size_detail: dict, gender: str):
    """
    根据性别，用 SIZE_RANGE_CONFIG['ecco'] 补齐缺失尺码：
    - 男款: 39–46
    - 女款: 35–42
    - 童款: 27–40
    TXT 中未出现的 EU 码统统补成无货:
        SizeMap[eu] = "无货"
        SizeDetail[eu] = {"stock_count": 0, "ean": "0000000000000"}
    """
    brand_cfg = SIZE_RANGE_CONFIG.get("ecco", {})
    key = None
    # ECCO 里 gender 是英文: "men" / "women" / "kids" / "unisex"
    if gender == "men":
        key = "男款"
    elif gender == "women":
        key = "女款"
    elif gender == "kids":
        key = "童款"
    else:
        # "unisex" 或未知，不补码，避免误判
        return size_map, size_detail

    standard_sizes = brand_cfg.get(key, [])
    if not standard_sizes:
        return size_map, size_detail

    for eu in standard_sizes:
        if eu not in size_detail:
            size_map[eu] = "无货"
            size_detail[eu] = {"stock_count": 0, "ean": "0000000000000"}

    return size_map, size_detail


def parse_ecco_sizes_and_stock(html: str):
    """
    从 ECCO 页面脚本中解析尺码+库存。
    - 先解析 variants[*].availability.channels.results 里 key=="GB-web" 的 availableQuantity
    - 再用 relatedProduct.variants[*] 回填缺失的 EU/UK/qty
    - 兼容 \\" 转义 和 未转义 两种形态
    返回: [{sku,size_eu,size_uk,available_qty,has_stock}, ...]（去重、按 EU 升序）
    """

    def _unescape(s: str) -> str:
        # 局部反转义，便于 demjson3 解析
        return s.replace('\\"', '"').replace('\\\\', '\\')

    rows = []

    # ---- A) variants 主渠道（有 GB-web 数量）----
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
                        "sku": sku,
                        "size_eu": str(size_eu),
                        "size_uk": str(size_uk) if size_uk is not None else "",
                        "available_qty": qty,
                        "has_stock": on
                    })
        except Exception:
            pass  # 不影响后续回填

    # ---- B) relatedProduct.variants 兜底回填 ----
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
            # 用 (sku, eu) 建索引便于合并
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
                    # 只有在 A 中没拿到 qty 时才用回填
                    if (r.get("available_qty") is None) or (r.get("available_qty") == 0):
                        r["available_qty"] = qty
                        r["has_stock"] = bool(has) if has is not None else (qty > 0)
                else:
                    rows.append({
                        "sku": sku,
                        "size_eu": eu,
                        "size_uk": uk,
                        "available_qty": qty,
                        "has_stock": bool(has) if has is not None else (qty > 0)
                    })
        except Exception:
            pass

    # ---- C) 清洗 & 排序 ----
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

    def _eu_key(s: str):
        try:
            return int(str(s).split("-")[0])
        except Exception:
            return 999

    cleaned.sort(key=lambda x: _eu_key(x.get("size_eu", "")))
    return cleaned


def extract_price_info(html):
    """
    返回 (Price, AdjustedPrice)
    1) 先走旧的 onProductPageInit()
    2) 回退 JSON-LD offers.price（AdjustedPrice 无则为 0）
    """
    # 旧逻辑
    try:
        m = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if m:
            data = json.loads(m.group(1).replace("&quot;", '"'))
            return float(data.get("Price", 0.0) or 0.0), float(data.get("AdjustedPrice", 0.0) or 0.0)
    except Exception:
        pass

    # JSON-LD 回退
    try:
        for s in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            j = json.loads(s.strip())
            if isinstance(j, dict) and j.get("@type") == "Product" and "offers" in j:
                offers = j["offers"]
                if isinstance(offers, dict) and "price" in offers:
                    price = float(str(offers.get("price", "0")).replace(",", "") or 0)
                    return price, 0.0
    except Exception:
        pass
    return 0.0, 0.0


def build_size_fields(rows):
    """
    rows -> 
      Product Size: "39,40,41,..."
      Product Size Detail: "39|uk:6|stock:64|sku:0194....;..."
    - 去重、排序；缺失字段用占位（uk:"", stock:0, sku:""）
    """
    eu_seen = set()
    eu_list, detail = [], []

    for r in rows:
        eu = str(r.get("size_eu") or "").strip()
        if not eu or eu in eu_seen:
            continue
        eu_seen.add(eu)
        eu_list.append(eu)

        uk  = str(r.get("size_uk") or "").strip()
        sku = str(r.get("sku") or "").strip()
        # 库存强制 int，避免 "92" 被当成非数字
        try:
            qty = int(r.get("available_qty") or 0)
        except Exception:
            qty = 0

        detail.append(f"{eu}|uk:{uk}|stock:{qty}|sku:{sku}")

    # 排序 & 同步排序 detail
    def _eu_key(s: str):
        try:
            return int(s.split("-")[0])
        except Exception:
            return 999

    eu_list.sort(key=_eu_key)
    order = {eu: i for i, eu in enumerate(eu_list)}
    detail.sort(key=lambda seg: order.get(seg.split("|", 1)[0], 999))

    return ",".join(eu_list), ";".join(detail)



def ensure_dirs(*paths: Path):
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

def is_url(s: str) -> bool:
    return str(s).startswith("http://") or str(s).startswith("https://")

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def get_meta(soup, name=None, prop=None):
    if name:
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            return clean(m["content"])
    if prop:
        m = soup.find("meta", attrs={"property": prop})
        if m and m.get("content"):
            return clean(m["content"])
    return ""

MATERIAL_WORDS = [
    "Leather", "Nubuck", "Suede", "Textile", "Mesh", "Canvas",
    "Rubber", "GORE-TEX", "Gore-Tex", "GORETEX", "Synthetic", "PU", "TPU", "EVA", "Wool", "Neoprene"
]

def guess_code_from_url(url: str) -> str:
    m = re.search(r"/(\d{6})/(\d{5})(?:[/?#]|$)", url or "")
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m2 = re.search(r"/product/(\d{10,12})(?:[/?#]|$)", url or "")
    if m2:
        return m2.group(1)
    return hashlib.md5((url or "").encode("utf-8")).hexdigest()[:10]

def save_debug_html(url: str, html: str, tag: str = "loaded"):
    if not DEBUG_SAVE_HTML:
        return
    ensure_dirs(DEBUG_DIR)
    code_hint = guess_code_from_url(url)
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"{ts}_{tag}_{code_hint}.html"
    (DEBUG_DIR / name).write_text(html or "", encoding="utf-8", errors="ignore")

def fetch_html(url_or_file: str) -> str:
    if not is_url(url_or_file):
        return Path(url_or_file).read_text(encoding="utf-8", errors="ignore")
    r = requests.get(url_or_file, headers=HDRS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text

# ============ 可选：Selenium ============
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

def fetch_html_selenium(url: str) -> str:
    d = get_driver()
    d.get(url)
    # 轻等待：新站首屏直出 + 少量动态
    time.sleep(1.2)
    return d.page_source

# ============ 解析：编码 / 名称 / 描述 / 颜色 / 性别 / 材质 ============
def extract_code(soup, url="") -> str:
    # A. JSON-LD（新版最稳）
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                for k in ("sku", "mpn", "productID", "productId"):
                    v = str(item.get(k, "")).strip()
                    if v:
                        m = re.search(r"(\d{6})\D*(\d{5})", v)
                        if m:
                            return f"{m.group(1)}{m.group(2)}"
                        m2 = re.search(r"\b(\d{10,12})\b", v)
                        if m2:
                            return m2.group(1)
        except Exception:
            pass
    # B. 可见“Product number:”老模板
    node = soup.find("div", class_="product_info__product-number")
    if node:
        t = clean(node.get_text(" ", strip=True))
        m = re.search(r"(\d{6})\D+(\d{5})", t)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m2 = re.search(r"\b(\d{10,12})\b", t)
        if m2:
            return m2.group(1)
    # C. URL 兜底
    href = get_meta(soup, prop="og:url") or get_meta(soup, name="twitter:url")
    if not href:
        href = url or ""
    m = re.search(r"/(\d{6})/(\d{5})(?:[/?#]|$)", href)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m2 = re.search(r"/product/(\d{10,12})(?:[/?#]|$)", href)
    if m2:
        return m2.group(1)
    # D. 整页兜底
    text = soup.get_text(" ", strip=True)
    m3 = re.search(r"\b(\d{6})\D{0,3}(\d{5})\b", text)
    if m3:
        return f"{m3.group(1)}{m3.group(2)}"
    m4 = re.search(r"\b(\d{10,12})\b", text)
    if m4:
        return m4.group(1)
    raise RuntimeError("Product Code not found")

def extract_names(soup):
    # 新模板：双标题
    h1 = soup.select_one('[data-testid="product-card-titleandprice"] h1')
    marketing = ""
    model = ""
    if h1:
        p = h1.find("p")
        marketing = clean(p.get_text(" ", strip=True)) if p else ""
        tails = [t for t in (h1.find_all(string=True, recursive=False) or [])]
        model = clean(tails[0]) if tails and clean(tails[0]) else ""
    # og:title 兜底（常见形如 "... | Black"）
    og_title = get_meta(soup, prop="og:title")
    if not (marketing or model) and og_title:
        # 去品牌 ECCO 文案粘连，保留 Men's/Women's
        left = og_title.split(" | ", 1)[0]
        left = re.sub(r"\bECCO\b|\bECCO®\b", "", left, flags=re.I)
        left = clean(left)
        marketing = left
    merged = " | ".join([x for x in [marketing, model] if x]) or (og_title or "")
    return marketing, model, merged

def extract_description(soup):
    # JSON-LD description 最干净
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                desc = item.get("description", "")
                if desc:
                    text = re.sub(r"<[^>]+>", " ", desc)
                    return clean(unescape(text))
        except Exception:
            pass
    # meta 描述兜底
    desc = get_meta(soup, name="description")
    if desc:
        text = re.sub(r"<[^>]+>", " ", desc)
        return clean(unescape(text))
    # 可见容器兜底
    node = soup.select_one("div.product-description")
    return clean(node.get_text(" ", strip=True)) if node else ""

def extract_color(soup):
    node = soup.select_one("span.product_info__color--selected")
    if node:
        return clean(node.get_text(" ", strip=True))
    og_title = get_meta(soup, prop="og:title")
    if " | " in og_title:
        return clean(og_title.split(" | ", 1)[1])
    return "No Data"

def parse_gender(*texts):
    t = " ".join([x or "" for x in texts]).lower()
    if "women" in t or "women’s" in t or "women's" in t or "ladies" in t:
        return "women"
    if "men" in t or "men’s" in t or "men's" in t:
        return "men"
    if "kid" in t or "junior" in t or "youth" in t:
        return "kids"
    return ""

def parse_materials(*texts):
    joined = " | ".join([x or "" for x in texts])
    hits = []
    for w in MATERIAL_WORDS:
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", joined, re.I):
            hits.append(w if w.isupper() else w.title())
    # 去重保序
    seen, out = set(), []
    for x in hits:
        xl = x.lower()
        if xl in seen: 
            continue
        seen.add(xl); out.append(x)
    return ", ".join(out) if out else "No Data"

# ============ 价格 / 库存 ============
def extract_prices(html, soup):
    """
    返回 (Price, AdjustedPrice)

    约定：
      - Price         = 原价（RRP），如果能拿到；
      - AdjustedPrice = 折后价（打折价），如果有打折，否则为 0。
    """

    def _parse_money(text: str) -> float:
        if not text:
            return 0.0
        m = re.search(r'(\d+(?:\.\d+)?)', text.replace(",", ""))
        return float(m.group(1)) if m else 0.0

    # 1) 旧逻辑：老站的 onProductPageInit
    try:
        m = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if m:
            js = m.group(1).replace("&quot;", '"')
            data = json.loads(js)
            p = float(data.get("Price", 0) or 0)
            ap = float(data.get("AdjustedPrice", 0) or 0)
            return p, ap
    except Exception:
        pass

    # 2) JSON-LD 中的当前价格（一般是折后价）
    current_price = 0.0
    try:
        for s in soup.find_all("script", {"type": "application/ld+json"}):
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                offers = item.get("offers")
                if isinstance(offers, dict) and "price" in offers:
                    current_price = float(str(offers.get("price", "0")).replace(",", "") or 0)
                    break
            if current_price:
                break
    except Exception:
        pass

    # 3) DOM 里的原价：<p data-testid="RecommendedPrice">£170.00</p>
    orig_price = 0.0
    try:
        p_orig = soup.find("p", attrs={"data-testid": "RecommendedPrice"})
        if p_orig:
            orig_price = _parse_money(p_orig.get_text(" ", strip=True))
    except Exception:
        pass

    # 3.1 优先用「原价 + 折后价」组合
    if orig_price > 0 and current_price > 0 and orig_price > current_price:
        return orig_price, current_price

    # 3.2 只有一个价格：当成原价
    if current_price > 0:
        return current_price, 0.0

    # 4) 兜底：只从 DOM 拿折后价（极少数没有 JSON-LD 的页面）
    try:
        p_disc = soup.select_one("p.product-price")
        disc_val = _parse_money(p_disc.get_text(" ", strip=True)) if p_disc else 0.0
        if orig_price > 0 and disc_val > 0 and orig_price > disc_val:
            return orig_price, disc_val
        if disc_val > 0:
            return disc_val, 0.0
    except Exception:
        pass

    # 5) 全部失败
    return 0.0, 0.0



def build_size_fields_jingya(rows):
    """
    将 parse_ecco_sizes_and_stock(rows) 的结果，转成鲸芽需要的两列：
      - Product Size:  EU:有货/无货;...
      - Product Size Detail: EU:3/0:EAN;...    (3=有货, 0=无货)
    规则：
      - 只看在线库存：qty>0 或 has_stock=True 视为有货 -> 状态码=3；否则=0
      - EAN/sku 不是 13 位时，用 '0000000000000' 占位
      - EU 尺码按数值升序；区间如 '3538' 可选转成 '35-38'（默认不改）
    """
    def eu_key(s):
        try:
            return int(str(s).split("-")[0])
        except Exception:
            return 999

    # 排序去重
    seen = set()
    sorted_rows = sorted(rows, key=lambda r: eu_key(r.get("size_eu", "")))

    size_parts = []
    detail_parts = []
    for r in sorted_rows:
        eu = str(r.get("size_eu") or "").strip()
        if not eu or eu in seen:
            continue
        seen.add(eu)

        qty = r.get("available_qty")
        has = r.get("has_stock")
        in_stock = (has is True) or (isinstance(qty, (int, float)) and qty > 0) or (isinstance(qty, str) and qty.isdigit() and int(qty) > 0)
        status_word = "有货" if in_stock else "无货"
        status_code = DEFAULT_STOCK_COUNT if in_stock else 0

        sku = str(r.get("sku") or "").strip()
        ean = sku if len(sku) == 13 and sku.isdigit() else "0000000000000"

        size_parts.append(f"{eu}:{status_word}")
        detail_parts.append(f"{eu}:{status_code}:{ean}")

    return ";".join(size_parts), ";".join(detail_parts)

def build_size_maps_jingya(rows):
    """
    rows -> (size_map, size_detail)
    - size_map:   {EU: "有货"/"无货", ...}
    - size_detail:{EU: {"stock_count": 3/0, "ean": "13位"}, ...}  # 3=有货,0=无货
    EAN 用 sku，非13位数字则给 "0000000000000"
    """
    def in_stock(r):
        q = r.get("available_qty")
        has = r.get("has_stock")
        if has is True:
            return True
        try:
            return int(q) > 0
        except Exception:
            return False

    size_map = {}
    size_detail = {}

    # 排序后去重
    def eu_key(s):
        try:
            return int(str(s).split("-")[0])
        except Exception:
            return 999

    seen = set()
    for r in sorted(rows, key=lambda x: eu_key(x.get("size_eu", ""))):
        eu = str(r.get("size_eu") or "").strip()
        if not eu or eu in seen:
            continue
        seen.add(eu)

        ok = in_stock(r)
        status_word = "有货" if ok else "无货"
        status_code = 3 if ok else 0

        sku = str(r.get("sku") or "").strip()
        ean = sku if (len(sku) == 13 and sku.isdigit()) else "0000000000000"

        size_map[eu] = status_word
        size_detail[eu] = {"stock_count": status_code, "ean": ean}

    return size_map, size_detail

def extract_sizes(html, soup):
    """
    返回 ["41:有货","42:无货", ...]
    - DOM: div.size-picker__rows button
    - 脚本 JSON 兜底: 查找包含 size / stock 的结构
    """
    results = []

    # DOM
    size_div = soup.find("div", class_="size-picker__rows")
    if size_div:
        for btn in size_div.find_all("button"):
            label = clean(btn.get_text(" ", strip=True))
            if not label:
                continue
            # ECCO UK 的尺码按钮多数直接显示 EU 码；若显示 UK，可在此加映射
            eu_m = re.search(r"\b(\d{2})\b", label)
            eu_size = eu_m.group(1) if eu_m else label
            classes = " ".join(btn.get("class", []))
            soldout = ("soldout" in classes.lower()) or ("disabled" in classes.lower()) or ("unavailable" in classes.lower())
            status = "无货" if soldout else "有货"
            results.append(f"{eu_size}:{status}")
        if results:
            return results

    # 脚本 JSON 兜底（尽量识别）
    for s in soup.find_all("script"):
        txt = s.string or ""
        if not txt:
            continue
        if ("size" in txt.lower() or "variant" in txt.lower()) and ("stock" in txt.lower() or "availability" in txt.lower()):
            # 提取 "EUxx" + availability
            # 常见字段：size, eu, available, inStock
            pairs = re.findall(r'("?(?:eu|size|label)"?\s*:\s*"?(\d{2})"?).*?("?(?:inStock|available|availability)"?\s*:\s*(?:true|false|"?(?:InStock|OutOfStock)"?))', txt, flags=re.I|re.S)
            added = set()
            for p in pairs:
                eu = p[1]
                avail_part = p[2].lower()
                soldout = ("false" in avail_part) or ("outofstock" in avail_part)
                status = "无货" if soldout else "有货"
                key = f"{eu}:{status}"
                if key not in added:
                    results.append(key)
                    added.add(key)
            if results:
                return results

    return results  # 可能为空（配件类无尺码）

# ============ 主流程 ============
def process_one(url: str, idx: int, total: int):
    try:
        print(f"🔍 ({idx}/{total}) {url}")
        # 1) 抓 HTML：requests 优先
        html = fetch_html(url)
        if DEBUG_SAVE_HTML:
            save_debug_html(url, html, "loaded_req")
        soup = BeautifulSoup(html, "html.parser")

        # 2) 极少数页回退 Selenium（若连 JSON-LD / og:title 都没有）
        need_fallback = False
        if not soup.find("script", {"type": "application/ld+json"}) and not get_meta(soup, prop="og:title"):
            need_fallback = True
        if ENABLE_SELENIUM and need_fallback and is_url(url):
            html = fetch_html_selenium(url)
            if DEBUG_SAVE_HTML:
                save_debug_html(url, html, "loaded_sel")
            soup = BeautifulSoup(html, "html.parser")

        # ===== 编码 / 名称 / 描述 / 颜色 =====
        product_code = extract_code(soup, url=url)
        marketing, model, merged_name = extract_names(soup)
        product_name = merged_name if merged_name else "No Data"
        description = extract_description(soup)
        color_name = extract_color(soup)

        # ===== 性别 / 材质（根据文本 & 尺码）=====
        gender_from_title = parse_gender(marketing, model, product_name)
        material_from_text = parse_materials(marketing, model, product_name, description)

        # ===== 新增：尺码 + 库存（优先 GB-web 数量；失败再 DOM 兜底）=====
        rows = parse_ecco_sizes_and_stock(html)  # ← 你已定义的函数
        
        size_map, size_detail = build_size_maps_jingya(rows)
        if not size_map:
            only_flags = extract_sizes(html, soup)  # ["41:有货","42:无货",...]
            for token in only_flags:
                if ":" not in token:
                    continue
                eu, flag = token.split(":", 1)
                eu = eu.strip()
                has = ("无货" not in flag)
                size_map[eu] = "有货" if has else "无货"
                size_detail[eu] = {"stock_count": DEFAULT_STOCK_COUNT if has else 0, "ean": "0000000000000"}

# 用尺码辅助判断性别（从 SizeMap 的尺码键推断）
        eu_sizes_arr     = [k for k in size_map.keys() if k.isdigit()]
        gender_by_size = ""
        if any(int(x) < 35 for x in eu_sizes_arr):
            gender_by_size = "kids"
        elif any(x in ("45", "46") for x in eu_sizes_arr):
            gender_by_size = "men"
        elif any(x in ("35", "36") for x in eu_sizes_arr):
            gender_by_size = "women"




        gender_by_size = ""
        if any(x.isdigit() and int(x) < 35 for x in eu_sizes_arr):
            gender_by_size = "kids"
        elif any(x in ("45", "46") for x in eu_sizes_arr):
            gender_by_size = "men"
        elif any(x in ("35", "36") for x in eu_sizes_arr):
            gender_by_size = "women"

        gender = gender_from_title or gender_by_size or "unisex"
        material = material_from_text or "No Data"

        # ✅ 在这里按 ECCO 标准尺码补码
        size_map, size_detail = supplement_ecco_sizes(size_map, size_detail, gender)

        # ===== 价格 =====
        price, adjusted = extract_prices(html, soup)

        # ===== 要点（Features）=====
        feature = ""
        li_texts = []
        for item in soup.select("div.chakra-accordion__item"):
            btn = item.find("button")
            if btn and "feature" in btn.get_text(strip=True).lower():
                panel = item.find("div", class_="chakra-accordion__panel")
                if panel:
                    for li in panel.select("ul li"):
                        t = clean(li.get_text(" ", strip=True))
                        if t:
                            li_texts.append(t)
                break
        if li_texts:
            feature = " | ".join(li_texts)

        # ===== 写文件（新增 Product Size Detail）=====
        ensure_dirs(TXT_DIR)
        out_path = TXT_DIR / f"{product_code}.txt"
        info = {
            "Product Code": product_code,
            "Product Name": product_name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color_name,
            "Product Price": price,
            "Adjusted Price": adjusted,
            "Product Material": material,
            "SizeMap": size_map,
            "SizeDetail": size_detail,
            "Feature": feature,
            "Source URL": url
        }
        format_txt(info, out_path, brand="clarks")
        print(f"✅ 写入: {out_path.name}")

    except Exception as e:
        print(f"❌ 失败: {url} -> {e}")
        try:
            err_html = html if 'html' in locals() else ""
        except Exception:
            err_html = ""
        if DEBUG_SAVE_HTML and err_html:
            save_debug_html(url, err_html, "error")
        try:
            ensure_dirs(TXT_DIR)
            code_hint = guess_code_from_url(url)
            out_path = TXT_DIR / f"{code_hint}.txt"
            info = {
                "Product Code": code_hint,
                "Product Name": "No Data",
                "Product Description": "",
                "Product Gender": "unisex",
                "Product Color": "No Data",
                "Product Price": 0.0,
                "Adjusted Price": 0.0,
                "Product Material": "No Data",
                "SizeMap": {},        # ← 必须是 dict
                "SizeDetail": {},     # ← 必须是 dict
                "Feature": "",
                "Source URL": url
            }
            format_txt(info, out_path, brand="clarks")
            print(f"⚠️ 已写占位: {out_path.name}")
        except Exception:
            pass


def ecco_fetch_info(links_file=None, max_workers: int = MAX_WORKERS):
    """
    ECCO 商品抓取入口。

    :param links_file: 可选，自定义 product_links.txt 路径。
                       为 None 时，使用 config 中的默认 LINKS_FILE。
    :param max_workers: 线程数，不传则使用默认 MAX_WORKERS。
    """
    # 1) 解析 links 文件路径
    if links_file is None:
        links_path = LINKS_FILE            # config 里的 Path
    else:
        links_path = Path(links_file)      # 允许传 str/path

    ensure_dirs(TXT_DIR, DEBUG_DIR)

    if not links_path.exists():
        raise FileNotFoundError(f"链接文件不存在: {links_path}")

    # 2) 读取 URL 列表
    urls = [u.strip() for u in links_path.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    print(f"📦 共 {total} 条，线程 {max_workers}，Selenium 回退: {ENABLE_SELENIUM}")
    if total == 0:
        print("⚠️ 链接文件为空，直接退出。")
        return

    # 3) 多线程抓取
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(process_one, url, i + 1, total) for i, url in enumerate(urls)]
        for _ in as_completed(futures):
            pass

    # 4) 关闭 selenium
    if ENABLE_SELENIUM:
        try:
            d = get_driver()
            d.quit()
        except Exception:
            pass

    print("✅ 完成")


if __name__ == "__main__":
    ecco_fetch_info()

