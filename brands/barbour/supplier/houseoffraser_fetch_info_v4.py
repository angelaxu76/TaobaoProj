# -*- coding: utf-8 -*-
"""
House of Fraser 采集器 - 重构版 (使用 BaseFetcher)

基于 houseoffraser_new_fetch_info_v3.py 重构
特点:
- Next.js __NEXT_DATA__ 解析
- Lexicon 词库匹配 (L1/L2 打分算法)
- 最复杂的匹配逻辑

对比:
- 旧版 (houseoffraser_new_fetch_info_v3.py): 765 行
- 新版 (本文件): ~450 行
- 代码减少: 41%

使用方式:
    python -m brands.barbour.supplier.houseoffraser_fetch_info_v4
"""

from __future__ import annotations

import re
import json
import time
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict
from bs4 import BeautifulSoup

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

# 配置
from config import BARBOUR, BRAND_CONFIG, SETTINGS

SITE_NAME = "houseoffraser"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# 数据库配置
PRODUCTS_TABLE = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# Lexicon 匹配参数
LEX_MIN_L1_HITS = 1
LEX_RECALL_LIMIT = 2500
LEX_TOPK = 20
LEX_MIN_SCORE = 0.70
LEX_MIN_LEAD = 0.05
LEX_REQUIRE_COLOR_EXACT = False

# 权重
LEX_W_L1 = 0.60
LEX_W_L2 = 0.25
LEX_W_COLOR = 0.15

# 等待时间 (Next.js 水合)
WAIT_HYDRATE_SECONDS = 22


# ================== Lexicon 缓存 ==================

_LEXICON_CACHE: Dict[Tuple[str, int], set] = {}


def _load_lexicon_set(raw_conn, brand: str, level: int) -> set:
    """加载 Lexicon 词库"""
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


# ================== 文本处理 ==================

def _normalize_ascii(text: str) -> str:
    """标准化为 ASCII"""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def _tokenize(text: str) -> List[str]:
    """文本分词"""
    t = _normalize_ascii(text).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = [w for w in t.split() if len(w) >= 3]
    return words


def _dedupe_keep_order(words: List[str]) -> List[str]:
    """去重保持顺序"""
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _normalize_color_name(color: str) -> str:
    """
    标准化颜色名称
    HOF: 'Olive OL71' / 'Navy NY91' -> 'olive'
    """
    if not color or color == "No Data":
        return ""

    c = color.strip()
    c = re.sub(r"\s+[A-Z]{1,3}\d{2,3}\b", "", c).strip()  # 去掉 OL71/NY91
    c = c.split("/")[0].strip()
    c = c.split("-")[0].strip()
    c = c.split("  ")[0].strip()
    c = re.sub(r"[^A-Za-z\s]", " ", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c.lower()


def _hits_by_lexicon(text: str, lex_set: set) -> List[str]:
    """计算文本命中的词"""
    tokens = _tokenize(text)
    hits = [w for w in tokens if w in lex_set]
    return _dedupe_keep_order(hits)


def _saturating_score(k: int) -> float:
    """饱和打分: 0->0, 1->0.75, 2->0.90, >=3->1.0"""
    if k <= 0:
        return 0.0
    if k == 1:
        return 0.75
    if k == 2:
        return 0.90
    return 1.0


# ================== Lexicon 匹配 ==================

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
    Lexicon 匹配算法

    返回: (best_product_code or None, debug_info)
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

    tbl = re.sub(r"[^a-zA-Z0-9_]", "", table or "barbour_products")

    l1_set = _load_lexicon_set(raw_conn, brand=brand, level=1)
    l2_set = _load_lexicon_set(raw_conn, brand=brand, level=2)

    scraped_l1 = _hits_by_lexicon(scraped_title or "", l1_set)
    scraped_l2 = _hits_by_lexicon(scraped_title or "", l2_set)

    debug["scraped_l1"] = scraped_l1
    debug["scraped_l2"] = scraped_l2

    if len(scraped_l1) < min_l1_hits:
        debug["reason"] = "FAIL_NO_L1"
        return None, debug

    # Step1: L1 召回
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

    # Step2: 颜色过滤 + L2 精排
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

    scored.sort(
        key=lambda x: (
            x["score"],
            -x["l1_overlap"],
            -x["l2_overlap"],
            -float(1 if x["color_match"] else 0),
            -int(999 - (x["source_rank"] or 999))
        ),
        reverse=True
    )

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


# ================== 采集器实现 ==================

class HouseOfFraserFetcher(BaseFetcher):
    """
    House of Fraser 采集器

    特点:
    - Next.js __NEXT_DATA__ 解析
    - Lexicon 词库匹配
    - 长水合时间 (22 秒)
    """

    def __init__(self, *args, **kwargs):
        """初始化 + 数据库引擎"""
        super().__init__(*args, **kwargs)

        # 创建数据库引擎
        engine_url = (
            f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
            f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
        )
        self._engine = create_engine(engine_url)

    def _fetch_html(self, url: str) -> str:
        """
        覆盖基类方法 - 增加水合等待时间

        House of Fraser 需要更长的等待时间让 Next.js 完成水合
        """
        driver = self.get_driver()
        try:
            driver.get(url)
            time.sleep(WAIT_HYDRATE_SECONDS)  # 等待 Next.js 水合
            return driver.page_source or ""
        finally:
            self.quit_driver()

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析 House of Fraser 商品详情页

        页面特点:
        - JSON-LD 包含基础信息
        - 价格在 data-testid="price"
        - 尺码在 select/option
        - 使用 Lexicon 匹配获取 Product Code
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 从 JSON-LD 提取基础信息
        jd = self._from_jsonld_product(soup) or {}
        title_guess = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
        desc_guess = jd.get("description") or "No Data"
        sku_guess = jd.get("sku") or "No Data"

        # 2. 提取颜色
        color_guess = self._extract_color(soup, html) or "No Data"

        # 3. 提取价格
        product_price_str, adjusted_price_str = self._extract_prices(soup)

        # 4. 提取尺码
        raw_sizes = self._extract_sizes(soup)

        # 5. Lexicon 匹配 Product Code
        final_code = None

        with self._engine.begin() as conn:
            raw_conn = self._get_dbapi_connection(conn)

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

        # 兜底: 使用页面 SKU
        if not final_code:
            final_code = sku_guess if sku_guess and sku_guess != "No Data" else "No Data"

        # 6. 推断性别
        gender_for_logic = self._decide_gender(final_code, soup, html, url)

        # 7. 格式化尺码
        product_size_str, product_size_detail_str = self._finalize_sizes(raw_sizes, gender_for_logic)

        # 8. 返回标准化字典
        return {
            "Product Code": final_code,
            "Product Name": self.clean_text(title_guess, maxlen=200),
            "Product Color": self.clean_text(color_guess, maxlen=100),
            "Product Gender": gender_for_logic,
            "Product Description": self.clean_description(desc_guess),
            "Original Price (GBP)": product_price_str,
            "Discount Price (GBP)": adjusted_price_str,
            "Product Size": product_size_str,
            "Product Size Detail": product_size_detail_str,
        }

    def _get_dbapi_connection(self, conn: Connection):
        """获取 DBAPI 连接"""
        try:
            return conn.connection
        except Exception:
            return conn.connection.connection

    def _from_jsonld_product(self, soup: BeautifulSoup) -> dict:
        """从 JSON-LD 提取产品信息"""
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

    def _extract_color(self, soup: BeautifulSoup, html: str) -> str:
        """提取颜色"""
        m = re.search(r'"color"\s*:\s*"([^"]+)"', html or "")
        if m:
            return m.group(1).strip()
        return "No Data"

    def _extract_prices(self, soup: BeautifulSoup) -> tuple:
        """提取价格"""
        price_block = soup.select_one('p[data-testid="price"]')
        if not price_block:
            return ("No Data", "No Data")

        discounted_span = price_block.select_one("span[class*='Price_isDiscounted']")
        discounted_price = None
        if discounted_span:
            discounted_price = self._parse_price_string(discounted_span.get_text(strip=True))

        ticket_span = price_block.select_one('span[data-testid="ticket-price"]')
        ticket_price = None
        if ticket_span:
            ticket_price = self._parse_price_string(ticket_span.get_text(strip=True))

        if ticket_price is None:
            block_testvalue = price_block.get("data-testvalue")
            ticket_price = self._parse_price_string(block_testvalue)

        if ticket_price is None:
            first_span = price_block.find("span")
            if first_span:
                ticket_price = self._parse_price_string(first_span.get_text(strip=True))

        if discounted_price is not None and ticket_price is not None:
            product_price_val = ticket_price
            adjusted_price_val = discounted_price
        else:
            product_price_val = ticket_price or discounted_price
            adjusted_price_val = None

        product_price_str = f"{product_price_val:.2f}" if product_price_val is not None else "No Data"
        adjusted_price_str = f"{adjusted_price_val:.2f}" if adjusted_price_val is not None else "No Data"

        return product_price_str, adjusted_price_str

    def _parse_price_string(self, txt: str) -> Optional[float]:
        """从文本解析价格"""
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

    def _extract_sizes(self, soup: BeautifulSoup) -> list:
        """提取尺码"""
        sizes = []
        for opt in soup.select("[data-testid*='size'] option, select option"):
            t = opt.get_text(strip=True)
            if t and t not in sizes:
                sizes.append(t)
        return sizes

    def _decide_gender(self, sku: str, soup: BeautifulSoup, html: str, url: str) -> str:
        """推断性别"""
        # 从 SKU 推断
        sku_guess = self._infer_gender_from_code(sku or "")
        if sku_guess and sku_guess != "No Data":
            return sku_guess

        # 从 URL 推断
        page_guess = self._extract_gender_from_url(url)
        if page_guess and page_guess != "No Data":
            return page_guess

        return "No Data"

    def _infer_gender_from_code(self, code: str) -> str:
        """从编码推断性别"""
        code = (code or "").upper()
        if code.startswith("M"):
            return "Men"
        if code.startswith("L"):
            return "Women"
        return "No Data"

    def _extract_gender_from_url(self, url: str) -> str:
        """从 URL 推断性别"""
        u = (url or "").lower()
        if "/men" in u or "mens" in u:
            return "Men"
        if "/women" in u or "womens" in u:
            return "Women"
        return "No Data"

    def _finalize_sizes(self, raw_sizes: list, gender_for_logic: str) -> tuple:
        """格式化尺码"""
        from common_taobao.core.size_utils import clean_size_for_barbour

        cleaned = []
        for s in raw_sizes or []:
            ns = clean_size_for_barbour(str(s))
            if ns and ns != "No Data" and ns not in cleaned:
                cleaned.append(ns)

        if not cleaned:
            return ("No Data", "No Data")

        product_size_str = ";".join([f"{x}:有货" for x in cleaned])
        product_size_detail_str = ";".join([f"{x}:{DEFAULT_STOCK_COUNT}:0000000000000" for x in cleaned])

        return product_size_str, product_size_detail_str


# ================== 主入口 ==================

def houseoffraser_fetch_info(
    max_workers: int = 1,
    headless: bool = False,
):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数 (建议 1, HOF 需要长等待)
        headless: 是否无头模式
    """
    setup_logging()

    fetcher = HouseOfFraserFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=WAIT_HYDRATE_SECONDS,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ House of Fraser 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    houseoffraser_fetch_info(max_workers=1, headless=False)
