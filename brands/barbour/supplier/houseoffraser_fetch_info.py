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
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import requests
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

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
        """
        重写：保留 #colcode=... fragment + 过滤已完成的 URL

        HoF 链接格式: .../product-123456#colcode=12345678
        基类 normalize_url 会把 # 后面全部删掉，导致 Selenium 打开时
        JS 无法读取 colcode，页面不知道该展示哪个颜色的尺码。
        这里直接读文件，只去空格和注释，保留 fragment。
        """
        try:
            raw_lines = self.links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            self.logger.error(f"读取链接文件失败: {e}")
            return []

        seen: set = set()
        all_urls: list = []

        for line in raw_lines:
            url = line.strip()
            if not url or url.startswith("#"):
                continue
            # 仅去除查询参数中的 tracking 参数，保留 #fragment
            # 简单去重：以完整 URL（含 fragment）为 key
            if url not in seen:
                seen.add(url)
                all_urls.append(url)

        before = len(all_urls)
        urls = [u for u in all_urls if u not in self._done_urls]
        skipped = before - len(urls)
        if skipped > 0:
            self.logger.info(f"⏭️ 跳过已完成 {skipped} 个，剩余 {len(urls)} 个待抓取")
        return urls

    def _fetch_html(self, url: str) -> str:
        """
        使用 Selenium 加载页面并等待 JS 渲染完成。

        HoF 是 Next.js App Router (RSC streaming) 站点，尺码/库存数据完全通过
        客户端 JS 渲染，requests 获取的静态 HTML 中没有任何尺码信息，
        必须用 Selenium 等待 JS 执行完毕后才能抓取。
        """
        driver = self.get_driver()
        driver.get(url)

        # 等待产品价格出现（表示 JS 已完成渲染）
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.find_elements("css selector", "p[data-testid='price'], [data-testid='price']")
                          or d.find_elements("css selector", "[class*='Price_']")
                          or d.find_elements("css selector", "[class*='price']")
            )
        except TimeoutException:
            self.logger.warning(f"等待价格元素超时 (30s)，继续解析: {url}")

        return driver.page_source

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
        - Next.js App Router SSR，尺码数据全部通过 JS 渲染
        - 价格在 data-testid="price"
        - 使用 Lexicon 匹配获取 Product Code
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 从 JSON-LD 提取基础信息
        jd = self._from_jsonld_product(soup) or {}
        title_guess = jd.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
        desc_guess = jd.get("description") or "No Data"
        sku_guess = jd.get("sku") or "No Data"

        # 2. 提取颜色
        color_guess = self._extract_color(soup, html, url=url) or "No Data"

        # 3. 提取价格
        product_price_str, adjusted_price_str = self._extract_prices(soup)

        # 4. 提取尺码 — 返回 {size: {stock_count, ean}} 格式
        size_detail_dict = self._extract_size_detail(soup)

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

        # 7. 格式化尺码（有货/无货均包含）
        product_size_str, product_size_detail_str = self.build_size_lines(size_detail_dict, gender_for_logic)

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

    def _extract_color(self, soup: BeautifulSoup, html: str, url: str = "") -> str:
        """提取颜色（从渲染后的 HTML 或 URL fragment 中的 colcode 提取）"""
        m = re.search(r'"color"\s*:\s*"([^"]+)"', html or "")
        if m:
            return m.group(1).strip()

        # 从 URL fragment 提取 colcode（HoF 格式：#colcode=54836103）
        if url:
            fm = re.search(r'[#&]colcode=([A-Za-z0-9]+)', url)
            if fm:
                return fm.group(1)

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

    # 有效尺码格式正则（编译一次复用）
    _SIZE_PATTERN = re.compile(
        r'^(XS|S|M|L|XL|2XL|XXL|XXXL|3XL|ONE SIZE|[0-9]{1,2}(\.[05])?|[0-9]{1,2}[RSL]?)$',
        re.IGNORECASE
    )

    def _extract_size_detail(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """
        提取尺码详情 dict，格式与其他供应商一致：
          {"S": {"stock_count": 3, "ean": "0000000000000"},
           "M": {"stock_count": 0, "ean": "0000000000000"}, ...}

        策略：
        1. BeautifulSoup 快速尝试（Selenium 渲染后 DOM 有效）
        2. 兜底：JavaScript 聚类法（按三级祖先容器分组，最大组 = 尺码选择器）
        JS 对每个元素同时判断有货/无货（aria-disabled / class / 删除线 / 透明度）。
        """
        from common.product.size_utils import clean_size_for_barbour

        # --- BeautifulSoup 快速路 ---
        bs4_detail = self._extract_size_detail_from_soup(soup)
        if bs4_detail:
            return bs4_detail

        # --- JS 聚类法 ---
        try:
            driver = self.get_driver()

            js = r"""
            var SIZE_PAT = /^(XS|S|M|L|XL|2XL|XXL|XXXL|3XL|ONE SIZE|[0-9]{1,2}(\.[05])?|[0-9]{1,2}[RSL]?)$/i;

            function getAncestor(el, levels) {
                var cur = el;
                for (var i = 0; i < levels; i++) {
                    if (!cur.parentElement) break;
                    cur = cur.parentElement;
                }
                return cur;
            }

            function isUnavailable(el) {
                if (el.disabled) return true;
                if (el.getAttribute('aria-disabled') === 'true') return true;
                var cls = (el.className || '').toLowerCase();
                if (cls.indexOf('unavailable') >= 0 || cls.indexOf('out-of-stock') >= 0 ||
                    cls.indexOf('sold-out') >= 0) return true;
                // 删除线 = 无货
                var style = window.getComputedStyle(el);
                var dec = style.textDecoration || style.webkitTextDecoration || '';
                if (dec.indexOf('line-through') >= 0) return true;
                // 极低透明度 = 无货
                var opacity = parseFloat(style.opacity || '1');
                if (opacity < 0.4) return true;
                return false;
            }

            var candidates = [];
            var els = document.querySelectorAll(
                'button, li, span, [role="option"], [role="radio"], input[type="radio"] + label'
            );

            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                var text = (el.textContent || '').trim();
                if (!SIZE_PAT.test(text)) continue;

                var unavail = isUnavailable(el);
                var ancestor = getAncestor(el, 3);
                candidates.push({ text: text, unavail: unavail, ancestor: ancestor });
            }

            // 按祖先容器分组（每组记录每个 size 及其有效库存标志）
            var groups = [];
            for (var j = 0; j < candidates.length; j++) {
                var c = candidates[j];
                var found = false;
                for (var k = 0; k < groups.length; k++) {
                    if (groups[k].ancestor === c.ancestor) {
                        // 同一尺码出现多次：有货优先
                        var existing = null;
                        for (var m = 0; m < groups[k].items.length; m++) {
                            if (groups[k].items[m].text === c.text) {
                                existing = groups[k].items[m];
                                break;
                            }
                        }
                        if (existing) {
                            if (!c.unavail) existing.unavail = false; // 有货优先
                        } else {
                            groups[k].items.push({ text: c.text, unavail: c.unavail });
                        }
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    groups.push({ ancestor: c.ancestor, items: [{ text: c.text, unavail: c.unavail }] });
                }
            }

            // 最大组 = 尺码选择器
            var bestItems = [];
            for (var g = 0; g < groups.length; g++) {
                if (groups[g].items.length > bestItems.length) {
                    bestItems = groups[g].items;
                }
            }

            return { items: bestItems };
            """

            result = driver.execute_script(js)
            if not result:
                return {}

            items = result.get("items", [])
            if not items:
                self.logger.warning("⚠️  JS 聚类法未找到尺码")
                return {}

            size_detail: Dict[str, Dict] = {}
            for item in items:
                raw = (item.get("text") or "").strip()
                cleaned = clean_size_for_barbour(raw) or raw
                if not cleaned:
                    continue
                unavail = item.get("unavail", False)
                stock = 0 if unavail else self.default_stock
                size_detail[cleaned] = {"stock_count": stock, "ean": "0000000000000"}

            self.logger.info(f"✅ JS 聚类提取到尺码: { {k: v['stock_count'] for k, v in size_detail.items()} }")
            return size_detail

        except Exception as e:
            self.logger.warning(f"JS 提取尺码失败: {e}")
            return {}

    def _extract_size_detail_from_soup(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """
        BeautifulSoup 快速路（Selenium 渲染后 DOM 中已有尺码元素时使用）。
        返回 {size: {stock_count, ean}} 或空 dict。
        """
        from common.product.size_utils import clean_size_for_barbour

        size_detail: Dict[str, Dict] = {}
        seen: set = set()

        selectors = [
            "button[data-testid*='size']",
            "button[data-testid*='Size']",
            "[data-testid='size-button']",
            "[class*='SizeButton']",
            "[class*='size-button']",
            "[data-testid='size-selector'] button",
            "[data-testid*='size'] option",
            "select option",
        ]

        for sel in selectors:
            elements = soup.select(sel)
            if not elements:
                continue

            for el in elements:
                text = (
                    el.get("data-size")
                    or el.get("data-value")
                    or el.get("data-attr-value")
                    or el.get("value")
                    or el.get_text(strip=True)
                )
                text = (text or "").strip()
                if not text or not self._SIZE_PATTERN.match(text):
                    continue

                cleaned = clean_size_for_barbour(text) or text
                if not cleaned or cleaned in seen:
                    continue
                seen.add(cleaned)

                classes = " ".join(el.get("class") or []).lower()
                disabled = el.has_attr("disabled") or el.get("aria-disabled") == "true"
                is_unavail = any(kw in classes for kw in ("unavailable", "unselectable", "not-available", "out-of-stock"))
                stock = 0 if (disabled or is_unavail) else self.default_stock
                size_detail[cleaned] = {"stock_count": stock, "ean": "0000000000000"}

            if size_detail:
                return size_detail

        return {}

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
