# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour - 新版 Next.js PDP 解析
- 不再尝试旧版；统一按新栈(JSON-LD + DOM)解析
- 单实例 Selenium（undetected-chromedriver），首个商品页等待10秒手动点 Cookie
- 输出沿用旧有 KV 文本模板，不改字段名/顺序，保证下游兼容
"""

from __future__ import annotations

import os, time, tempfile, threading, html as ihtml
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict

# ---- 依赖 ----
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

# ---- 项目内模块（保持不变）----
from config import BARBOUR, BRAND_CONFIG
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from brands.barbour.core.sim_matcher import match_product, choose_best
from common_taobao.core.size_utils import clean_size_for_barbour as _norm_size  # 尺码清洗
from common_taobao.core.driver_auto import build_uc_driver

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


import json
from bs4 import BeautifulSoup


WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50，特意不包含52

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS",  "XS": "XS",
    "S": "S", "SMALL":"S",
    "M": "M", "MEDIUM":"M",
    "L": "L", "LARGE":"L",
    "XL": "XL", "X-LARGE":"XL",
    "XXL":"2XL","2XL":"2XL",
    "XXXL":"3XL","3XL":"3XL",
}


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
            if n in {4,6,8,10,12,14,16,18,20}:
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



def _choose_size_family_for_gender(gender: str, observed_sizes: set[str]) -> list[str]:
    """
    决定我们要输出/补全的“这一套尺码体系”的顺序列表。
    - 女款：固定 4..20
    - 男款：在字母系(2XS..3XL) 和 数字系(30..50) 之间二选一
      - 如果两种都有，则看哪个出现的数量更多
    """

    g = (gender or "").lower()
    if "女" in g:
        return WOMEN_ORDER[:]

    has_num   = any(k in MEN_NUM_ORDER   for k in observed_sizes)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in observed_sizes)

    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]

    if has_num or has_alpha:
        num_count   = sum(1 for k in observed_sizes if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in observed_sizes if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]

    # 实在看不出来，就默认字母系
    return MEN_ALPHA_ORDER[:]


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
    返回 list[str]，来自 sizes.allSizes[].size。会对 size 做 _norm_size 清洗并去重保序。
    """
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
                size = _norm_size(raw) or raw   # ← 清洗
                if size not in seen:
                    seen.add(size)
                    sizes.append(size)
        except Exception:
            pass
    return sizes



def _extract_sizes_dom_fallback(soup: BeautifulSoup):
    """
    从渲染后的尺寸按钮容器抓取：
    - data-testid="swatch-button-enabled" => 有货
    - data-testid="swatch-button-disabled" => 无货
    会对 size 做 _norm_size 清洗并去重。
    """
    enabled = []
    disabled = []

    for btn in soup.select('[data-testid="swatch-button-enabled"]'):
        raw = (btn.get("value") or btn.get_text() or "").strip()
        if not raw: 
            continue
        size = _norm_size(raw) or raw  # ← 清洗
        enabled.append(size)

    for btn in soup.select('[data-testid="swatch-button-disabled"], button[disabled][data-testid*="swatch"]'):
        raw = (btn.get("value") or btn.get_text() or "").strip()
        if not raw:
            continue
        size = _norm_size(raw) or raw  # ← 清洗
        disabled.append(size)

    if not enabled and not disabled:
        return []

    # 去重保序；有货优先
    seen = set()
    entries = []
    for s in enabled:
        if s not in seen:
            seen.add(s); entries.append((s, "有货"))
    for s in disabled:
        if s not in seen:
            seen.add(s); entries.append((s, "无货"))

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
    status = "有货"/"无货"（以 isOnStock 为准）。会对 size 做 _norm_size 清洗。
    """
    entries = []
    patt = r'"size"\s*:\s*"([^"]+?)".{0,4000}?"isOnStock"\s*:\s*(true|false)'
    for m in re.finditer(patt, html, re.S | re.I):
        raw = m.group(1).strip()
        size = _norm_size(raw) or raw  # ← 清洗
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

import re
from typing import Tuple, Dict, Optional
from bs4 import BeautifulSoup

OOS_WORDS = ["out of stock", "sold out", "unavailable", "no stock", "oos"]

def _is_number_size(label: str) -> bool:
    # 纯数字，比如 "44", "46", "32", "30"
    return bool(re.fullmatch(r"\d+", label.strip()))

def _is_letter_size(label: str) -> bool:
    # 常见衣服字母码，包括 3XL / 4XL / XXL / XXXL 等
    norm = label.strip().upper()
    # 明确常见集合
    COMMON = [
        "2XS","XXS","XS",
        "S","M","L",
        "XL","XXL","2XL",
        "XXXL","3XL","4XL","5XL"
    ]
    return norm in COMMON

def _extract_sizes_new(soup: BeautifulSoup) -> Dict[str, Dict[str, int]]:
    """
    抓 House of Fraser / Flannels 页面上的尺码按钮，返回中间结构:
    {
        "12": {"stock": 3},
        "14": {"stock": 3},
        "16": {"stock": 3},
        "XS": {"stock": 0},
        ...
    }
    注意：这里不做清洗/不做补全/不管男女，只负责原始抓取。
    后面会由 normalize+补码 的流程来生成最终 Product Size / Product Size Detail。
    """

    results: Dict[str, Dict[str, int]] = {}

    # swatch 按钮是我们最可靠的来源
    for btn in soup.select("button[data-testid='swatch-button-enabled'], button[data-testid='swatch-button-disabled']"):
        # label 尺码名，比如 "12 (M)" / "16(XL)" / "XL" / "2XL"
        label = (btn.get("value") or btn.get_text() or "").strip()
        if not label:
            continue

        # 判断库存
        data_tid = btn.get("data-testid", "")
        in_stock = "enabled" in data_tid  # enabled = 可选，有货；disabled = 无货
        stock_qty = 3 if in_stock else 0

        # 记录（后面会继续清洗）
        if label not in results:
            results[label] = {"stock": stock_qty}
        else:
            # 多次出现，保留有货那个
            if results[label]["stock"] == 0 and stock_qty > 0:
                results[label]["stock"] = stock_qty

    return results



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
    has_num   = any(k in MEN_NUM_ORDER   for k in observed_sizes)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in observed_sizes)

    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]

    if has_num or has_alpha:
        num_count   = sum(1 for k in observed_sizes if k in MEN_NUM_ORDER)
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

    # 2. 选定应该用哪一套完整尺码表（女款固定 4..20，男款在两套男码体系里选）
    observed = set(normalized_stock.keys())
    full_order = _choose_size_family_for_gender(gender or "", observed)

    # 3. 把不在该体系里的码剔除（防止 "12" 跟 "M" 混在一起）
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
        size_detail_parts.append(f"{size_token}:{3 if qty > 0 else 0}:{EAN_PLACEHOLDER}")

    product_size_str = ";".join(size_line_parts) if size_line_parts else "No Data"
    product_size_detail_str = ";".join(size_detail_parts) if size_detail_parts else "No Data"

    return product_size_str, product_size_detail_str






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




def _parse_price_string(txt: str) -> float | None:
    """
    输入类似 '£189.00' / '189.00' / '18900' / '189'
    返回 float，比如 189.0
    """
    if not txt:
        return None

    import re

    cleaned = txt.strip()
    # 优先：直接带£的，比如 £189.00
    m_symbol = re.search(r"£\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_symbol:
        return float(m_symbol.group(1))

    # 其次：data-testvalue="18900" 这种分里面是分(pence)，需要/100
    m_pence = re.search(r"^([0-9]{3,})$", cleaned)
    if m_pence:
        try:
            pence_val = int(m_pence.group(1))
            return round(pence_val / 100.0, 2)
        except:
            pass

    # 最后兜底：纯数字小数
    m_plain = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_plain:
        return float(m_plain.group(1))

    return None


def _extract_prices_new(soup: BeautifulSoup) -> tuple[str, str]:
    """
    返回 (product_price_str, adjusted_price_str)
    - product_price_str => 我们TXT里的 Product Price (原价)
    - adjusted_price_str => 我们TXT里的 Adjusted Price (折后价 / 没打折则 'No Data')
    """

    price_block = soup.select_one('p[data-testid="price"]')
    if not price_block:
        return ("No Data", "No Data")

    # 1. 折后价 (现价)
    #    只有在打折的时候才会有 class 包含 Price_isDiscounted__
    discounted_span = price_block.select_one("span[class*='Price_isDiscounted']")
    discounted_price = None
    if discounted_span:
        discounted_price = _parse_price_string(discounted_span.get_text(strip=True))

    # 2. 原价
    #    原价通常在 data-testid="ticket-price"
    ticket_span = price_block.select_one('span[data-testid="ticket-price"]')
    ticket_price = None
    if ticket_span:
        ticket_price = _parse_price_string(ticket_span.get_text(strip=True))

    # 3. 如果没有 ticket-price，可能是没打折，
    #    那就直接看整个 price_block 自己的 data-testvalue 或纯文本
    if ticket_price is None:
        # 尝试 data-testvalue="17900"
        block_testvalue = price_block.get("data-testvalue")
        ticket_price = _parse_price_string(block_testvalue)

    if ticket_price is None:
        # 尝试把 <p> 里面第一个 span 的文本当成原价
        first_span = price_block.find("span")
        if first_span:
            ticket_price = _parse_price_string(first_span.get_text(strip=True))

    # 现在我们有:
    #   discounted_price (可能 None)
    #   ticket_price (不应该是 None 了，除非页面真的出问题)

    if discounted_price is not None and ticket_price is not None:
        # 有折扣场景：
        # Product Price = 原价 (ticket_price)
        # Adjusted Price = 折后价 (discounted_price)
        product_price_val = ticket_price
        adjusted_price_val = discounted_price
    else:
        # 无折扣场景：
        # Product Price = 唯一那个价
        # Adjusted Price = "No Data"
        product_price_val = ticket_price or discounted_price
        adjusted_price_val = None

    # 格式化成字符串；保持两位小数或 "No Data"
    product_price_str = (
        f"{product_price_val:.2f}" if product_price_val is not None else "No Data"
    )
    adjusted_price_str = (
        f"{adjusted_price_val:.2f}" if adjusted_price_val is not None else "No Data"
    )

    return product_price_str, adjusted_price_str




def _decide_gender_for_logic(sku: str, soup: BeautifulSoup, html: str, url: str) -> str:
    """
    返回标准英文性别，优先级：
    1. 根据 SKU 猜 (最稳定，LQUxxx = women, MQUxxx = men)
    2. 如果 SKU 猜不到，再尝试页面上的性别提取 _extract_gender_new(...)
    3. 如果还猜不到，返回 "No Data"

    返回值只可能是: "women", "men", "kids", "unisex", or "No Data"
    （按你们sku规则一般就是 men / women / No Data）
    """

    # 1. SKU 推断
    sku_guess = _infer_gender_from_code(sku or "")
    # 假设 _infer_gender_from_code 返回类似 "women", "men", 或 "No Data"
    if sku_guess and sku_guess != "No Data":
        return sku_guess

    # 2. 其次尝试页面
    page_guess = _extract_gender_new(soup, html, url)
    if page_guess and page_guess != "No Data":
        return page_guess

    # 3. 兜底
    return "No Data"




# ================== 核心解析 ==================
def parse_info_new(html: str, url: str, conn) -> Dict[str, Any]:
    """
    统一出口：这里产出的 info 就是最终要写进 TXT 的内容。
    关键点：
      1. 我们在这里就确定最终 Product Code（用缓存/DB匹配）。
      2. 用最终 Product Code 推断 gender_for_logic。
      3. 用 gender_for_logic 生成完整尺码表 Product Size / Product Size Detail。
      4. 把 Gender 直接转成中文（男款/女款/...）。

    参数:
        html: 当前商品页完整 HTML
        url:  当前商品页 URL
        conn: SQLAlchemy Connection (process_url_with_driver 里传进来的 conn)
    """
    soup = BeautifulSoup(html, "html.parser")

    # ---------- (A) 基础页面信息（不依赖数据库） ----------
    # 从 JSON-LD 把基础字段抓出来：name / description / sku 等
    jd = _from_jsonld_product_new(soup) or {}
    title_guess = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc_guess  = jd.get("description") or "No Data"
    sku_guess   = jd.get("sku") or "No Data"

    # 颜色：我们有 _extract_color_new (先看页面 JSON 里的color，再兜底 og:image:alt)
    color_guess = _extract_color_new(soup, html) or "No Data"

    # 尺码原始抓取（页面上所有尺码按钮，带 stock>0 or 0）
    raw_sizes = _extract_sizes_new(soup)  # dict like { "12(M)": {"stock":3}, "14(L)": {"stock":3}, ... }

    # 价格（"Product Price" / "Adjusted Price" 口径）
    product_price_str, adjusted_price_str = _extract_prices_new(soup)

    # ---------- (B) 基于 URL / DB 确定最终 Product Code ----------
    norm_url = _normalize_url(url)

    # 1. 先试 URL→Code 缓存
    final_code = URL_CODE_CACHE.get(norm_url)

    # 2. 如果缓存没有，用 DB 模糊匹配 (match_product + choose_best)
    if not final_code:
        # match_product 需要原始连接
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

    # 3. 如果还是拿不到，就退回 JSON-LD 里的 sku_guess
    if not final_code:
        final_code = sku_guess if sku_guess and sku_guess != "No Data" else "No Data"

    # ---------- (C) 用最终 code 判断性别 ----------
    # 我们现在用的是最终 code，而不是一开始的 sku_guess
    gender_for_logic = _decide_gender_for_logic(final_code, soup, html, url)
    # _decide_gender_for_logic 会：
    #   1. 用 _infer_gender_from_code(final_code) 判断 men/women
    #   2. 如果还不行，再看页面 JSON/DOM
    #   3. 实在不行才 "No Data"

    # ---------- (D) 用性别生成最终尺码串 ----------
    # 注意：_finalize_sizes_for_hof 会：
    #   - 清洗各类乱七八糟的尺码 ("12(M)" -> "12", "XL" -> "XL", "32" -> "32")
    #   - 根据 gender_for_logic 选整套尺码全集（女款=4..20；男款=2XS..3XL 或 30..50）
    #   - 给没出现的尺码补 "无货" / 0:0000000000000
    product_size_str, product_size_detail_str = _finalize_sizes_for_hof(raw_sizes, gender_for_logic)

    # ---------- (E) 把 gender_for_logic 变成中文展示 ----------
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

    # ---------- (F) 组装最终 info ----------
    info = {
        "Product Code":        final_code or "No Data",
        "Product Name":        title_guess or "No Data",
        "Product Description": desc_guess or "No Data",
        "Product Gender":      gender_display or "No Data",
        "Product Color":       color_guess or "No Data",

        "Product Price":       product_price_str,
        "Adjusted Price":      adjusted_price_str,

        # 暂时没做材质细分，保持原行为
        "Product Material":    "No Data",

        # 你原本硬编码了 "casual wear"，保持不变，避免下游崩
        "Style Category":      "casual wear",

        # 你原代码里写的是 "Feature": "No Data"
        "Feature":             "No Data",

        "Product Size":        product_size_str,
        "Product Size Detail": product_size_detail_str,

        "Source URL":          url,
        "Site Name":           SITE_NAME,
    }

    return info








# ================== Selenium 基础 ==================
def get_driver(headless: bool = False):
    """
    使用 TaobaoProj 的通用自动驱动：build_uc_driver
    - 自动检测本机 Chrome 主版本
    - 自动选择正确驱动
    - 自动清除 uc 缓存
    - 更稳定，避免 WinError 10060 / session not created
    """
    extra = [
        "--disable-blink-features=AutomationControlled",
        "--lang=en-GB",
        "accept-language=en-GB,en-US;q=0.9,en;q=0.8",
    ]
    return build_uc_driver(headless=headless, extra_options=extra, verbose=True)


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
    """
    打开单个 URL，解析出 info（已经包含最终 Product Code / Gender / 尺码等），
    然后写入 TXT。

    相比旧版本：
    - 不再这里做 URL→Code 匹配、gender 兜底，这些都提前放进了 parse_info_new。
    - 不再重复 _gender_to_cn，因为 parse_info_new 里已经把性别转成 "男款"/"女款"。
    """

    print(f"\n🌐 正在抓取: {url}")

    # 1. 打开页面并等待渲染完成
    driver.get(url)
    ok = wait_pdp_ready(driver, timeout=WAIT_HYDRATE_SECONDS)
    if not ok:
        # 页面可能还没完全hydrated，我们仍然抓当前HTML做兜底
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="timeout_debug")
    else:
        # 页面 ready 的情况下多滚几下，确保尺码/价格等JS渲染出来
        _soft_scroll(driver, steps=6, pause=0.4)
        html = driver.page_source or ""
        _dump_debug_html(html, url, tag="debug_new")

    # 2. 直接用新的 parse_info_new 解析完整信息（含最终code/性别/尺码）
    info = parse_info_new(html, url, conn)

    # 3. 选输出文件名
    code_for_filename = info.get("Product Code") or "NoDataCode"
    code_for_filename = code_for_filename.strip() or "NoDataCode"
    safe_code_for_filename = _safe_name(code_for_filename)

    # 如果真的没拿到标准code（还是 "No Data"），我们 fallback 用hash+商品名生成文件名
    if safe_code_for_filename in ("NoDataCode", "No_Data", "NoData", "No", ""):
        short = f"{abs(hash(url)) & 0xFFFFFFFF:08x}"
        safe_name_part = _safe_name(info.get("Product Name") or "BARBOUR")
        out_path = TXT_DIR / f"{safe_name_part}_{short}.txt"
    else:
        out_path = TXT_DIR / f"{safe_code_for_filename}.txt"

    # 4. 写 TXT (保持你原来的字段顺序和格式)
    payload = _kv_txt_bytes(info)
    ok_write = _atomic_write_bytes(payload, out_path)

    if ok_write:
        print(f"✅ 写入: {out_path} (code={info.get('Product Code')})")
    else:
        print(f"❗ 放弃写入: {out_path.name}")

    # 5. 小延迟，防止被风控
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
