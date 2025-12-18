# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour - PDP 解析（V4）
V4 目标：
  1) 把“匹配决策过程”独立出来（common_taobao.matching.hybrid_barbour_matcher）
  2) 每个 URL 输出一份 debug json（可开关），快速定位匹配率低的原因
  3) 颜色匹配/模糊匹配逻辑复用你现有模块（color_code_resolver / sim_matcher）

你原 V3 的字段输出/写 TXT 逻辑不改，保证下游兼容。
"""

from __future__ import annotations

import os, time, tempfile, threading
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

import re
import json
import unicodedata
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from config import BARBOUR, BRAND_CONFIG, SETTINGS
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from common_taobao.core.size_utils import clean_size_for_barbour as _norm_size

# ★ V4：匹配逻辑独立模块
from brands.barbour.core.hybrid_barbour_matcher import resolve_product_code, dump_debug_trace

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
MAX_WORKERS_DEFAULT = 1

# ====== V4：debug 开关 ======
WRITE_MATCH_DEBUG_JSON = True   # True 时，每个 URL 生成 *_match.json，便于统计原因
MATCH_DEBUG_TOPN = 5

# ====== 匹配阈值（你后面可调） ======
SIM_MIN_SCORE = 0.72
SIM_MIN_LEAD = 0.04

LEX_MIN_L1_HITS = 1
LEX_MIN_SCORE = 0.68
LEX_MIN_LEAD = 0.04
LEX_REQUIRE_COLOR_EXACT = False  # 建议 False，提高召回；颜色当加分项

# ================== URL→Code 缓存（可选） ==================
URL_CODE_CACHE: Dict[str, str] = {}
_URL_CODE_CACHE_READY = False

# ================== 尺码相关常量（保留） ==================
WOMEN_ORDER = ["4", "6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA_ORDER = ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

# ================== DB 辅助 ==================
def get_dbapi_connection(conn: Connection):
    try:
        return conn.connection
    except Exception:
        return conn.connection.connection

def _normalize_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"#.*$", "", u)
    return u

def _safe_name(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s)
    return s[:120].strip("_") or "NoData"

def _atomic_write_bytes(data: bytes, path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return True
    except Exception:
        return False

def _kv_txt_bytes(info: Dict[str, Any]) -> bytes:
    lines = []
    for k, v in info.items():
        if isinstance(v, (list, tuple)):
            vv = ";".join([str(x) for x in v])
        else:
            vv = str(v) if v is not None else "No Data"
        lines.append(f"{k}: {vv}")
    return ("\n".join(lines) + "\n").encode("utf-8")

# ================== 解析函数（沿用 V3 的思路，尽量不改） ==================
def _from_jsonld_product_new(soup: BeautifulSoup) -> dict:
    out = {}
    try:
        for s in soup.select('script[type="application/ld+json"]'):
            raw = s.get_text(strip=True)
            if not raw:
                continue
            data = json.loads(raw)
            if isinstance(data, list):
                for obj in data:
                    if isinstance(obj, dict) and obj.get("@type") in ("Product", "product"):
                        data = obj
                        break
            if isinstance(data, dict) and data.get("@type") in ("Product", "product"):
                out["name"] = data.get("name")
                out["description"] = data.get("description")
                out["sku"] = data.get("sku")
                break
    except Exception:
        pass

    if not out.get("name"):
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
            return round(int(m_pence.group(1)) / 100.0, 2)
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
    discounted_price = _parse_price_string(discounted_span.get_text(strip=True)) if discounted_span else None

    ticket_span = price_block.select_one('span[data-testid="ticket-price"]')
    ticket_price = _parse_price_string(ticket_span.get_text(strip=True)) if ticket_span else None

    if ticket_price is None:
        ticket_price = _parse_price_string(price_block.get("data-testvalue"))

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

def _extract_color_new(soup: BeautifulSoup, html: str) -> str:
    m = re.search(r'"color"\s*:\s*"([^"]+)"', html or "")
    if m:
        return m.group(1).strip()
    return "No Data"

def _extract_sizes_new(soup: BeautifulSoup) -> list[str]:
    sizes = []
    for opt in soup.select("[data-testid*='size'] option, select option"):
        t = opt.get_text(strip=True)
        if t and t not in sizes:
            sizes.append(t)
    return sizes

def _infer_gender_from_code(code: str) -> str:
    code = (code or "").upper()
    if code.startswith("M"):
        return "Men"
    if code.startswith("L"):
        return "Women"
    return "No Data"

def _extract_gender_new(soup: BeautifulSoup, html: str, url: str) -> str:
    u = (url or "").lower()
    if "/men" in u or "mens" in u:
        return "Men"
    if "/women" in u or "womens" in u:
        return "Women"
    return "No Data"

def _decide_gender_for_logic(sku: str, soup: BeautifulSoup, html: str, url: str) -> str:
    sku_guess = _infer_gender_from_code(sku or "")
    if sku_guess and sku_guess != "No Data":
        return sku_guess
    page_guess = _extract_gender_new(soup, html, url)
    if page_guess and page_guess != "No Data":
        return page_guess
    return "No Data"

def _finalize_sizes_for_hof(raw_sizes: list[str], gender_for_logic: str) -> tuple[str, str]:
    cleaned = []
    for s in raw_sizes or []:
        ns = _norm_size(str(s))
        if ns and ns != "No Data" and ns not in cleaned:
            cleaned.append(ns)
    if not cleaned:
        return ("No Data", "No Data")
    product_size_str = ";".join([f"{x}:有货" for x in cleaned])
    product_size_detail_str = ";".join([f"{x}:{DEFAULT_STOCK_COUNT}:0000000000000" for x in cleaned])
    return product_size_str, product_size_detail_str

def _dump_debug_html(html: str, url: str, tag: str = "debug_new"):
    try:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        p = DEBUG_DIR / f"{tag}_{short}.html"
        p.write_text(html or "", encoding="utf-8", errors="ignore")
    except Exception:
        pass

# ================== driver / fetch（保留） ==================
_DRIVER_LOCK = threading.Lock()

def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    user_data_dir = tempfile.mkdtemp(prefix="hof_profile_")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver

def fetch_html_with_driver(driver, url: str) -> str:
    driver.get(url)
    time.sleep(WAIT_HYDRATE_SECONDS)
    return driver.page_source or ""

def build_url_code_cache(raw_conn, products_table: str, offers_table: Optional[str], site_name: str):
    global _URL_CODE_CACHE_READY, URL_CODE_CACHE
    if _URL_CODE_CACHE_READY:
        return
    # 你原项目里有更完整实现的话，直接替换这里即可
    _URL_CODE_CACHE_READY = True

def _write_match_debug_json(url: str, trace: dict, *, code_for_filename: str, product_name: str):
    if not WRITE_MATCH_DEBUG_JSON:
        return
    try:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        safe_code = _safe_name(code_for_filename or "NoDataCode")
        safe_title = _safe_name(product_name or "BARBOUR")
        p = DEBUG_DIR / f"match_{safe_code}_{short}.json"
        # 只保留 top N，避免文件太大
        for step in trace.get("steps", []):
            if step.get("stage") == "sim_matcher" and isinstance(step.get("top"), list):
                step["top"] = step["top"][:MATCH_DEBUG_TOPN]
            if step.get("stage") == "lexicon":
                detail = step.get("detail") or {}
                if isinstance(detail.get("top"), list):
                    detail["top"] = detail["top"][:MATCH_DEBUG_TOPN]
        dump_debug_trace(trace, p, ensure_ascii=False)
    except Exception:
        pass

# ================== 关键：parse_info_new（V4 只改匹配段落） ==================
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

    raw_conn = get_dbapi_connection(conn)

    # ======= V4：统一匹配入口（可输出完整 trace）=======
    trace = None
    if not final_code:
        final_code, trace = resolve_product_code(
            raw_conn,
            site_name=SITE_NAME,
            url=norm_url,
            scraped_title=title_guess or "",
            scraped_color=color_guess or "",
            sku_guess=sku_guess,
            products_table=PRODUCTS_TABLE,
            offers_table=OFFERS_TABLE,
            url_code_cache=URL_CODE_CACHE,
            brand="barbour",
            debug=True,
            sim_min_score=SIM_MIN_SCORE,
            sim_min_lead=SIM_MIN_LEAD,
            lex_min_l1_hits=LEX_MIN_L1_HITS,
            lex_min_score=LEX_MIN_SCORE,
            lex_min_lead=LEX_MIN_LEAD,
            lex_require_color_exact=LEX_REQUIRE_COLOR_EXACT,
        )

    gender_for_logic = _decide_gender_for_logic(final_code, soup, html, url)
    product_size_str, product_size_detail_str = _finalize_sizes_for_hof(raw_sizes, gender_for_logic)

    out = OrderedDict()
    out["Site Name"] = SITE_NAME
    out["Source URL"] = url
    out["Product Code"] = final_code
    out["Product Name"] = title_guess or "No Data"
    out["Product Color"] = color_guess or "No Data"
    out["Product Gender"] = gender_for_logic or "No Data"
    out["Product Description"] = desc_guess or "No Data"
    out["Original Price (GBP)"] = product_price_str or "No Data"
    out["Discount Price (GBP)"] = adjusted_price_str or "No Data"
    out["Product Size"] = product_size_str or "No Data"
    out["Product Size Detail"] = product_size_detail_str or "No Data"

    # 写 debug json（与 TXT 分离，不污染下游解析）
    if trace:
        _write_match_debug_json(url, trace, code_for_filename=final_code, product_name=title_guess or "")

    return out

def process_url_with_driver(driver, url: str, conn: Connection, delay: float = 0.0) -> Optional[Path]:
    try:
        html = fetch_html_with_driver(driver, url)
    except Exception:
        return None

    _dump_debug_html(html, url, tag="debug_new")

    info = parse_info_new(html, url, conn)

    code_for_filename = info.get("Product Code") or "NoDataCode"
    safe_code_for_filename = _safe_name(str(code_for_filename).strip() or "NoDataCode")

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

# ================== 主入口：多线程版本（保留） ==================
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
    print(f"📄 共 {total} 个商品页面待解析.（并发 {max_workers}）")
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
            print("🕒 将打开首个商品页。请在 10 秒内手动点击 Cookie 的 'Allow all' 按钮.")
            driver.get(first_url)
            time.sleep(10)
            print("✅ 已等待 10 秒，开始正式抓取（首个商品仍然串行处理）")

            print(f"[启动] [1/{total}] {first_url}")
            with engine.begin() as conn:
                try:
                    path = process_url_with_driver(driver, first_url, conn=conn, delay=delay)
                    if path:
                        ok += 1
                    else:
                        fail += 1
                except Exception as e:
                    print(f"❌ 失败: {first_url} | {e}")
                    fail += 1

            try:
                driver.quit()
            except Exception:
                pass

            first_processed = True

        rest = urls[1:] if first_processed else urls
        if not rest:
            print(f"✅ 完成. 成功 {ok}, 失败 {fail}")
            return

        def _worker(u: str):
            d = get_driver(headless=headless)
            try:
                with engine.begin() as conn:
                    print(f"[启动] {u}")
                    return process_url_with_driver(d, u, conn=conn, delay=delay)
            finally:
                try:
                    d.quit()
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_worker, u): u for u in rest}
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    path = fut.result()
                    if path:
                        ok += 1
                    else:
                        fail += 1
                except Exception as e:
                    print(f"❌ 失败: {u} | {e}")
                    fail += 1

        print(f"✅ 完成. 成功 {ok}, 失败 {fail}")

    except KeyboardInterrupt:
        print("⛔ 中断。")

if __name__ == "__main__":
    houseoffraser_fetch_info(max_workers=1, headless=False)
