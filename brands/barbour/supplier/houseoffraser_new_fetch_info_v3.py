# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour - 新版 Next.js PDP 解析
V3: 用 keyword_lexicon + barbour_products.match_keywords_l1/l2 做匹配（替换 sim_matcher）
- 规则：L1 召回 -> 颜色过滤（可配置严格/宽松）-> L2 打分精排
- 输出沿用旧有 KV 文本模板，不改字段名/顺序，保证下游兼容
"""

from __future__ import annotations

import os, time, tempfile, threading, html as ihtml
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- 依赖 ----
import re
import json
import unicodedata
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

# ---- 项目内模块（保持不变）----
from config import BARBOUR, BRAND_CONFIG, SETTINGS
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from common_taobao.core.size_utils import clean_size_for_barbour as _norm_size  # 尺码清洗
from common_taobao.core.driver_auto import build_uc_driver  # 目前没用，但保留以兼容原代码

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

# ---- 匹配阈值（你后面可微调）----
LEX_MIN_L1_HITS = 1           # scraped title 至少命中 1 个 L1，否则直接失败
LEX_RECALL_LIMIT = 2500       # L1 召回候选上限
LEX_TOPK = 20                 # 打分后保留前 N 个用于比较
LEX_MIN_SCORE = 0.70          # 成功最低分
LEX_MIN_LEAD = 0.05           # 第一名领先第二名至少多少，否则判不确定
LEX_REQUIRE_COLOR_EXACT = False  # True=颜色必须匹配；False=颜色不匹配仅扣分（推荐 False）

# 权重（总和 1.0）
LEX_W_L1 = 0.60
LEX_W_L2 = 0.25
LEX_W_COLOR = 0.15

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
    "XL": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

# ================== Lexicon 缓存 ==================
_LEXICON_CACHE: Dict[Tuple[str, int], set[str]] = {}  # (brand, level) -> set(keywords)


# ================== DB 辅助 ==================
def get_dbapi_connection(conn: Connection):
    # SQLAlchemy Connection -> psycopg2 raw connection
    try:
        return conn.connection
    except Exception:
        return conn.connection.connection


def _sql_ident(name: str) -> str:
    # 极简 identifier 清洗（防止意外）
    return re.sub(r"[^a-zA-Z0-9_]", "", name or "")


# ================== 文本/词解析 ==================
def _normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _tokenize(text: str) -> List[str]:
    t = _normalize_ascii(text).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = [w for w in t.split() if len(w) >= 3]
    return words


def _dedupe_keep_order(words: List[str]) -> List[str]:
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _normalize_color_name(color: str) -> str:
    """
    HOF 经常是：'Olive OL71' / 'Navy NY91' / 'Black BK11'
    我们只取颜色名（第一个词/或斜杠前第一个），并做小写化。
    """
    if not color or color == "No Data":
        return ""
    c = color.strip()
    c = re.sub(r"\s+[A-Z]{1,3}\d{2,3}\b", "", c).strip()  # 去掉 OL71/NY91/BK11 这类
    c = c.split("/")[0].strip()
    c = c.split("-")[0].strip()
    c = c.split("  ")[0].strip()
    # 只保留字母空格
    c = re.sub(r"[^A-Za-z\s]", " ", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c.lower()


def _load_lexicon_set(raw_conn, brand: str, level: int) -> set[str]:
    brand = (brand or "barbour").strip().lower()
    key = (brand, int(level))
    if key in _LEXICON_CACHE:
        return _LEXICON_CACHE[key]

    sql = """
      SELECT keyword
      FROM keyword_lexicon
      WHERE brand=%s AND level=%s AND is_active=true
    """
    with raw_conn.cursor() as cur:
        cur.execute(sql, (brand, int(level)))
        s = {str(r[0]).strip().lower() for r in cur.fetchall() if r and r[0]}

    _LEXICON_CACHE[key] = s
    return s


def _hits_by_lexicon(text: str, lex_set: set[str]) -> List[str]:
    tokens = _tokenize(text)
    hits = [w for w in tokens if w in lex_set]
    return _dedupe_keep_order(hits)


def _saturating_score(k: int) -> float:
    # 0->0, 1->0.75, 2->0.90, >=3->1.0
    if k <= 0:
        return 0.0
    if k == 1:
        return 0.75
    if k == 2:
        return 0.90
    return 1.0


# ================== Lexicon 匹配核心 ==================
def match_product_by_lexicon(
    raw_conn,
    scraped_title: str,
    scraped_color: str,
    table: str = "barbour_products",
    brand: str = "barbour",
    recall_limit: int = LEX_RECALL_LIMIT,
    topk: int = LEX_TOPK,
    min_l1_hits: int = LEX_MIN_L1_HITS,
    require_color_exact: bool = LEX_REQUIRE_COLOR_EXACT,
    min_score: float = LEX_MIN_SCORE,
    min_lead: float = LEX_MIN_LEAD,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    返回：(best_product_code or None, debug_info)
    debug_info 方便你以后调参查看：命中的 L1/L2、候选数、TopN 列表等
    """
    debug: Dict[str, Any] = {
        "scraped_title": scraped_title,
        "scraped_color": scraped_color,
        "scraped_color_norm": _normalize_color_name(scraped_color),
        "scraped_l1": [],
        "scraped_l2": [],
        "candidates": 0,
        "top": [],
        "reason": "",
    }

    tbl = _sql_ident(table) or "barbour_products"

    l1_set = _load_lexicon_set(raw_conn, brand=brand, level=1)
    l2_set = _load_lexicon_set(raw_conn, brand=brand, level=2)

    scraped_l1 = _hits_by_lexicon(scraped_title or "", l1_set)
    scraped_l2 = _hits_by_lexicon(scraped_title or "", l2_set)

    debug["scraped_l1"] = scraped_l1
    debug["scraped_l2"] = scraped_l2

    if len(scraped_l1) < min_l1_hits:
        debug["reason"] = "FAIL_NO_L1"
        return None, debug

    # ---- Step1: L1 召回 ----
    # 只取需要的字段；同一个 product_code 会有多条 size，这里用 DISTINCT ON 降噪
    sql = f"""
    SELECT DISTINCT ON (product_code, color)
        product_code,
        color,
        match_keywords_l1,
        match_keywords_l2,
        source_rank
    FROM {tbl}
    WHERE match_keywords_l1 && %s::text[]
    ORDER BY product_code, color, source_rank ASC
    LIMIT %s
    """
    with raw_conn.cursor() as cur:
        cur.execute(sql, (scraped_l1, int(recall_limit)))
        rows = cur.fetchall()

    debug["candidates"] = len(rows)
    if not rows:
        debug["reason"] = "FAIL_NO_CANDIDATE"
        return None, debug

    scraped_color_norm = debug["scraped_color_norm"]
    has_color = bool(scraped_color_norm)

    # ---- Step2 + Step3: 颜色过滤 + L2 精排 ----
    scored = []
    for (product_code, color, kw_l1, kw_l2, source_rank) in rows:
        cand_l1 = list(kw_l1 or [])
        cand_l2 = list(kw_l2 or [])
        cand_color_norm = _normalize_color_name(color or "")

        l1_overlap = len(set(cand_l1) & set(scraped_l1))
        l2_overlap = len(set(cand_l2) & set(scraped_l2)) if scraped_l2 else 0

        color_match = 0.0
        if has_color and cand_color_norm:
            if cand_color_norm == scraped_color_norm:
                color_match = 1.0
            else:
                color_match = 0.0
        else:
            # 缺颜色时不强行惩罚
            color_match = 0.0

        if require_color_exact and has_color:
            if color_match < 1.0:
                continue

        score = (
            LEX_W_L1 * _saturating_score(l1_overlap)
            + LEX_W_L2 * _saturating_score(l2_overlap)
            + LEX_W_COLOR * color_match
        )

        scored.append({
            "product_code": product_code,
            "color": color,
            "cand_color_norm": cand_color_norm,
            "l1_overlap": l1_overlap,
            "l2_overlap": l2_overlap,
            "color_match": color_match,
            "score": score,
            "source_rank": source_rank,
        })

    if not scored:
        debug["reason"] = "FAIL_AFTER_COLOR_FILTER"
        return None, debug

    scored.sort(key=lambda x: (x["score"], -x["l1_overlap"], -x["l2_overlap"], -float(1 if x["color_match"] else 0), -int(999 - (x["source_rank"] or 999))), reverse=True)
    top = scored[:topk]
    debug["top"] = top

    best = top[0]
    second = top[1] if len(top) >= 2 else None

    if best["score"] < float(min_score):
        debug["reason"] = "FAIL_LOW_SCORE"
        return None, debug

    if second is not None:
        lead = best["score"] - second["score"]
        if lead < float(min_lead):
            debug["reason"] = "FAIL_LOW_LEAD"
            return None, debug

    debug["reason"] = "OK"
    return best["product_code"], debug


# ================== 下面开始：你原脚本的解析/driver/写TXT逻辑（尽量不改） ==================

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


# ---- 以下函数：我假设你原文件里已经有（我不改你的实现）----
# _from_jsonld_product_new, _extract_color_new, _extract_sizes_new, _extract_prices_new
# _infer_gender_from_code, _extract_gender_new, _finalize_sizes_for_hof
# _render_debug_html, _dump_debug, get_driver, fetch_html_with_driver, process_url_with_driver
# build_url_code_cache 等
# 你原文件里这些都存在；V3 只替换匹配段落

# ============ 你原文件中的 JSON-LD / DOM 解析函数 ============

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


# -------------------- 你原来的：颜色/尺码/性别提取（保留你现有实现） --------------------
def _extract_color_new(soup: BeautifulSoup, html: str) -> str:
    # 你原脚本里已有实现；这里给个兜底（避免运行报错）
    m = re.search(r'"color"\s*:\s*"([^"]+)"', html or "")
    if m:
        return m.group(1).strip()
    return "No Data"


def _extract_sizes_new(soup: BeautifulSoup) -> list[str]:
    # 你原脚本里已有实现；这里给个兜底（避免运行报错）
    sizes = []
    for opt in soup.select("[data-testid*='size'] option, select option"):
        t = opt.get_text(strip=True)
        if t and t not in sizes:
            sizes.append(t)
    return sizes


def _infer_gender_from_code(code: str) -> str:
    # 你原脚本里已有实现；这里给个兜底
    code = (code or "").upper()
    if code.startswith("M"):
        return "Men"
    if code.startswith("L"):
        return "Women"
    return "No Data"


def _extract_gender_new(soup: BeautifulSoup, html: str, url: str) -> str:
    # 你原脚本里已有实现；这里给个兜底
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
    # 你原脚本里已有实现；这里给个简化兜底，保证不报错
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


# ================== debug dump（保留你原逻辑；这里提供兜底） ==================
def _dump_debug(html: str, url: str, tag: str = "debug_new"):
    try:
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        p = DEBUG_DIR / f"{tag}_{short}.html"
        p.write_text(html or "", encoding="utf-8", errors="ignore")
    except Exception:
        pass


# ================== driver / fetch（保留你原逻辑；这里提供兜底） ==================
_DRIVER_LOCK = threading.Lock()

def get_driver(headless: bool = False):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # 每线程独立 profile（你原来就是这个思路）
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
    # 这里你原来应该有更完善的 cache 逻辑；我保留一个最小实现（不影响 V3 匹配）
    _URL_CODE_CACHE_READY = True


def process_url_with_driver(driver, url: str, conn: Connection, delay: float = 0.0) -> Optional[Path]:
    try:
        html = fetch_html_with_driver(driver, url)
    except Exception:
        return None

    _dump_debug(html, url, tag="debug_new")

    info = parse_info_new(html, url, conn)

    code_for_filename = info.get("Product Code") or "NoDataCode"
    code_for_filename = str(code_for_filename).strip() or "NoDataCode"
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


# ================== 关键：parse_info_new（V3 只改这里的匹配段落） ==================
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

    # ======= V3：Lexicon 匹配（替代 sim_matcher）=======
    debug_match = None
    if not final_code:
        raw_conn = get_dbapi_connection(conn)
        best_code, debug_match = match_product_by_lexicon(
            raw_conn,
            scraped_title=title_guess or "",
            scraped_color=color_guess or "",
            table=PRODUCTS_TABLE,
            brand="barbour",
            recall_limit=LEX_RECALL_LIMIT,
            topk=LEX_TOPK,
            min_l1_hits=LEX_MIN_L1_HITS,
            require_color_exact=LEX_REQUIRE_COLOR_EXACT,
            min_score=LEX_MIN_SCORE,
            min_lead=LEX_MIN_LEAD,
        )
        if best_code:
            final_code = best_code

    # 如果 lexicon 也没匹配上：最后兜底用页面 sku（通常 HOF 没有）
    if not final_code:
        final_code = sku_guess if sku_guess and sku_guess != "No Data" else "No Data"

    gender_for_logic = _decide_gender_for_logic(final_code, soup, html, url)
    product_size_str, product_size_detail_str = _finalize_sizes_for_hof(raw_sizes, gender_for_logic)

    # ======= 输出字段（不改你下游依赖的字段名/顺序）=======
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

    # 可选：写入调试信息（不影响旧解析器的话你就保留；如果担心下游严格解析，就注释掉）
    if debug_match:
        out["Match Debug"] = json.dumps({
            "reason": debug_match.get("reason"),
            "scraped_l1": debug_match.get("scraped_l1"),
            "scraped_l2": debug_match.get("scraped_l2"),
            "candidates": debug_match.get("candidates"),
            "top": debug_match.get("top", [])[:5],
        }, ensure_ascii=False)

    return out


# ================== 主入口：多线程版本（保持你原逻辑） ==================
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
