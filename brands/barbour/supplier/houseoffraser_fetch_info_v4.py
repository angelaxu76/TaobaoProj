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
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import requests

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# 导入统一匹配器
from brands.barbour.core.hybrid_barbour_matcher import resolve_product_code

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

# Lexicon 匹配参数（传给 hybrid_barbour_matcher）
LEX_MIN_L1_HITS = 1
LEX_MIN_SCORE = 0.70
LEX_MIN_LEAD = 0.05
LEX_REQUIRE_COLOR_EXACT = False

# 等待时间 (Next.js 水合)
WAIT_HYDRATE_SECONDS = 12


# ================== 采集器实现 ==================

class HouseOfFraserFetcher(BaseFetcher):
    """
    House of Fraser 采集器

    特点:
    - Next.js __NEXT_DATA__ 解析
    - hybrid_barbour_matcher 多级匹配
    - 断点续传 (自动跳过已完成的 URL)
    """

    # requests 模式的 User-Agent 和 session（共享连接池）
    _REQ_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    def __init__(self, *args, use_requests: bool = True, **kwargs):
        """
        初始化

        Args:
            use_requests: True = 用 requests 快速抓取 (默认);
                          False = 用 Selenium (兜底，适合反爬严重时)
        """
        super().__init__(*args, **kwargs)
        self._use_requests = use_requests
        self._session = requests.Session()
        self._session.headers.update(self._REQ_HEADERS)

        # 创建数据库引擎
        engine_url = (
            f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
            f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
        )
        self._engine = create_engine(engine_url, pool_size=self.max_workers + 2)

        # 断点续传：进度文件
        self._progress_file = Path(self.output_dir) / ".done_urls.txt"
        self._done_urls = self._load_done_urls()
        self._progress_lock = threading.Lock()

    # ================== 断点续传 ==================

    def _load_done_urls(self) -> set:
        """加载已完成的 URL 集合"""
        if not self._progress_file.exists():
            return set()
        try:
            lines = self._progress_file.read_text(encoding="utf-8").splitlines()
            done = {line.strip() for line in lines if line.strip()}
            self.logger.info(f"📋 已完成 {len(done)} 个，自动跳过")
            return done
        except Exception:
            return set()

    def _mark_done(self, url: str) -> None:
        """记录已完成的 URL（线程安全、追加写入）"""
        with self._progress_lock:
            self._done_urls.add(url)
            try:
                with open(self._progress_file, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
            except Exception:
                pass

    def _load_urls(self) -> List[str]:
        """重写：加载链接并过滤掉已完成的"""
        all_urls = super()._load_urls()
        before = len(all_urls)
        urls = [u for u in all_urls if u not in self._done_urls]
        skipped = before - len(urls)
        if skipped > 0:
            self.logger.info(f"⏭️ 跳过已完成 {skipped} 个，剩余 {len(urls)} 个待抓取")
        return urls

    def _fetch_html(self, url: str) -> str:
        """
        获取 HTML：优先用 requests（快），失败时回退 Selenium。

        HOF 是 Next.js SSR 站点，JSON-LD / __NEXT_DATA__ 都在首次 HTML 中，
        大多数情况不需要 JS 渲染。
        """
        if self._use_requests:
            try:
                resp = self._session.get(url, timeout=15)
                resp.raise_for_status()
                html = resp.text
                # 检查 HTML 是否包含有效数据（非空壳 / 反爬页）
                if '"@type"' in html or "__NEXT_DATA__" in html:
                    return html
                self.logger.debug(f"requests 返回无效页面，回退 Selenium: {url}")
            except Exception as e:
                self.logger.debug(f"requests 失败 ({e})，回退 Selenium: {url}")

        # 回退 Selenium
        return super()._fetch_html(url)

    def fetch_one_product(self, url: str, idx: int, total: int):
        """重写：成功后记录进度"""
        result = super().fetch_one_product(url, idx, total)
        url_out, success = result
        if success:
            self._mark_done(url_out)
        return result

    # ================== 页面解析 ==================

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

        # 5. hybrid_barbour_matcher 多级匹配 Product Code
        with self._engine.begin() as conn:
            raw_conn = self._get_dbapi_connection(conn)

            final_code, debug_trace = resolve_product_code(
                raw_conn,
                site_name=SITE_NAME,
                url=url,
                scraped_title=title_guess or "",
                scraped_color=color_guess or "",
                sku_guess=sku_guess,
                products_table=PRODUCTS_TABLE,
                offers_table=OFFERS_TABLE,
                brand="barbour",
                lex_min_l1_hits=LEX_MIN_L1_HITS,
                lex_min_score=LEX_MIN_SCORE,
                lex_min_lead=LEX_MIN_LEAD,
                lex_require_color_exact=LEX_REQUIRE_COLOR_EXACT,
            )

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
            "Product Price": product_price_str,          # txt_writer / DB 导入使用此 key
            "Adjusted Price": adjusted_price_str,        # txt_writer / DB 导入使用此 key
            "Original Price (GBP)": product_price_str,  # BaseFetcher._validate_info 要求
            "Discount Price (GBP)": adjusted_price_str, # BaseFetcher._validate_info 要求
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
        from common.product.size_utils import clean_size_for_barbour

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
    max_workers: int = 4,
    headless: bool = True,
    use_requests: bool = True,
):
    """
    主函数

    Args:
        max_workers: 并发线程数 (默认 4)
        headless: 是否无头模式 (默认 True，节省资源)
        use_requests: 是否用 requests 快速抓取 (默认 True)
                      设 False 可回退到纯 Selenium 模式
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
        use_requests=use_requests,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ House of Fraser 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    houseoffraser_fetch_info(max_workers=4, headless=True)
