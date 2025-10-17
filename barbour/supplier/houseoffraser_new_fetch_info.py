# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour 商品抓取（新版 Next.js 页面）
- 不再尝试旧版；统一按新栈解析（JSON-LD + DOM 兜底）
- 复用单个浏览器实例；批处理前给 10 秒手动点击 Cookie
- 输出保持与旧脚本一致的 KV 文本格式
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
OFFERS_TABLE: Optional[str] = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")  # 允许不存在
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# ================== 参数 ==================
WAIT_HYDRATE_SECONDS = 22
DEFAULT_DELAY = 0.0
MAX_WORKERS_DEFAULT = 1  # 复用单 driver，默认串行更稳；如需并发，改为每线程1个driver
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

# ================== 新版解析：等待 & 解析 ==================
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
        # price
        "[data-testid*='price']",
        "[data-component*='price']",
        "[itemprop='price']",
        "meta[itemprop='price']",
        # title
        "h1",
        "[data-testid*='title']",
        "[data-component*='title']",
        # sizes
        "button[aria-pressed][data-testid*='size']",
        "li[role='option']",
        "option[data-testid*='drop-down-option']",
        "#sizeDdl option",
        # JSON-LD 也算信号
        "script[type='application/ld+json']",
    ])
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.find_elements(By.CSS_SELECTOR, key_css):
                return True
        except Exception:
            pass
        _soft_scroll(driver, steps=2, pause=0.4)
    return False

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
        # description 可能包含 html
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

def _extract_sizes_new(soup: BeautifulSoup) -> Tuple[str, str]:
    entries = []

    # 1) 按按钮型
    for btn in soup.select("button[aria-pressed][data-testid*='size']"):
        txt = (btn.get_text() or "").strip()
        if not txt: continue
        disabled = (btn.get("disabled") is not None) or (btn.get("aria-disabled") in ("true", "True"))
        status = "无货" if disabled else "有货"
        size_norm = _norm_size(txt)
        if size_norm: entries.append((size_norm, status))

    # 2) 列表/下拉型
    if not entries:
        for li in soup.select("li[role='option']"):
            txt = (li.get_text() or "").strip()
            if not txt: continue
            disabled = li.get("aria-disabled") in ("true", "True") or "disabled" in (li.get("class") or [])
            status = "无货" if disabled else "有货"
            size_norm = _norm_size(txt)
            if size_norm: entries.append((size_norm, status))

    if not entries:
        for opt in soup.select("option[data-testid*='drop-down-option'], #sizeDdl option"):
            raw_label = (opt.get_text() or "").strip()
            if not raw_label or raw_label.lower().startswith("select"): continue
            clean_label = re.sub(r"\s*-\s*Out\s*of\s*stock\s*$", "", raw_label, flags=re.I).strip(" -/")
            size_norm = _norm_size(clean_label)
            if not size_norm: continue
            oos = opt.has_attr("disabled") or (opt.get("aria-disabled") == "true") or "out of stock" in raw_label.lower()
            entries.append((size_norm, "无货" if oos else "有货"))

    if not entries:
        return "No Data", "No Data"

    # 去重 & 组装（与旧版格式一致）
    by_size: Dict[str, str] = {}
    for sz, st in entries:
        prev = by_size.get(sz)
        if prev is None or (prev == "无货" and st == "有货"):
            by_size[sz] = st
    ordered = list(dict.fromkeys([sz for sz, _ in entries]))
    EAN = "0000000000000"
    product_size = ";".join(f"{s}:{by_size[s]}" for s in ordered) or "No Data"
    product_size_detail = ";".join(f"{s}:{3 if by_size[s]=='有货' else 0}:{EAN}" for s in ordered) or "No Data"
    return product_size, product_size_detail

def parse_info_new(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    jd = parse_jsonld(html)  # 优先 JSON-LD

    # 标题/描述/品牌/价格
    title = jd.get("title")
    if not title:
        h1 = soup.select_one("h1,[data-testid*='title'],[data-component*='title']")
        title = h1.get_text(strip=True) if h1 else "No Data"

    desc = jd.get("description") or "No Data"

    # 价格：JSON-LD price 是“当前价”（折后价）。原价需从 DOM 补齐
    curr_price = None
    if jd.get("price"):
        try: curr_price = float(str(jd["price"]).replace(",", ""))
        except Exception: pass

    # DOM 补齐：原价（ticket/original）
    orig_price = None
    price_el = soup.select_one("[data-testid*='ticket-price'], [data-component*='ticket'], .price-was, .wasPrice, .rrp")
    if price_el:
        orig_price = _to_num(price_el.get_text(" ", strip=True))

    # 如果没有原价，退化为用当前价充当
    if orig_price is None and curr_price is not None:
        orig_price = curr_price
    if curr_price is None and orig_price is not None:
        curr_price = orig_price

    # 颜色（以当前变体/色卡为准；DOM 更可靠）
    color = "No Data"
    color_el = soup.select_one("[data-testid*='colour'] [data-testid*='value'], [data-component*='colour']")
    if color_el:
        color = _clean(color_el.get_text())
    # 兜底：从标题里抽颜色（可选）
    if color == "No Data":
        m = re.search(r"\b(Black|Navy|Green|Olive|Brown|Blue|Red|Cream|Beige|Grey|Gray|White)\b", title or "", re.I)
        if m: color = m.group(1)

    # 性别：优先 JSON/类目，其次 URL 推断
    gender = "No Data"
    # URL 推断
    lower_url = url.lower()
    if "/women" in lower_url or "womens" in lower_url:
        gender = "Womens"
    elif "/men" in lower_url or "mens" in lower_url:
        gender = "Mens"

    # 尺码
    product_size, product_size_detail = _extract_sizes_new(soup)

    info = {
        "Product Code": jd.get("sku") or "No Data",
        "Product Name": title or "No Data",
        "Product Description": desc or "No Data",
        "Product Gender": gender,
        "Product Color": color or "No Data",
        "Product Price": f"{orig_price:.2f}" if isinstance(orig_price, (int, float)) else "No Data",
        "Adjusted Price": f"{curr_price:.2f}" if isinstance(curr_price, (int, float)) else "No Data",
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
    # 对齐英区环境，减少分流
    options.add_argument("--lang=en-GB")
    options.add_argument("accept-language=en-GB,en-US;q=0.9,en;q=0.8")
    return uc.Chrome(options=options)

def fetch_product_info_with_single_driver(driver, url: str) -> Dict[str, Any]:
    driver.get(url)
    ok = wait_pdp_ready(driver, timeout=WAIT_HYDRATE_SECONDS)
    if not ok:
        # 尽力而为，也保存一份调试
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

    # —— 编码获取：先查缓存（URL→Code），命中则跳过模糊匹配 —— #
    norm_url = _normalize_url(url)
    code = URL_CODE_CACHE.get(norm_url)
    if code:
        print(f"🔗 缓存命中 URL→{code}（跳过模糊匹配）")
        info["Product Code"] = code
    else:
        # 未命中 → 走模糊匹配（沿用你原来的阈值/逻辑）
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

    # ★ 启动阶段仅构建一次缓存（offers + products）
    with engine.begin() as conn:
        raw = get_dbapi_connection(conn)
        build_url_code_cache(raw, PRODUCTS_TABLE, OFFERS_TABLE, SITE_NAME)

    # —— 单实例浏览器：给你手动点 Cookie —— #
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
