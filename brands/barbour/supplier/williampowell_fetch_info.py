# -*- coding: utf-8 -*-
"""
William Powell (williampowell.com) 采集器

站点特点 (Shopify):
- 用普通 requests + 浏览器 UA 即可访问, 无需 Selenium
- 每个商品详情页有对应的干净 JSON 接口:
    https://williampowell.com/products/<handle>.js
  直接给出 price / compare_at_price (原价) / variants[].available (真实库存)
  / variants[].title (尺码), 比解析渲染后的 DOM 可靠得多
- 页面上不显示 Barbour 官方编码 (只有站内自己的 SKU, 如 "MJC176-RUS-S"),
  所以 Product Code 通过 hybrid_barbour_matcher.resolve_product_code() 用
  "标题 + 颜色" 去 barbour_products 表做模糊匹配获取 (做法与
  houseoffraser_fetch_info.py 一致)

使用方式:
    python -m brands.barbour.supplier.williampowell_fetch_info
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from brands.barbour.core.color_utils import COLOR_MAP, normalize_color
from brands.barbour.core.hybrid_barbour_matcher import resolve_product_code

from config import BARBOUR, BRAND_CONFIG, SETTINGS

SITE_NAME = "williampowell"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

PRODUCTS_TABLE = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# Lexicon 匹配参数（与 houseoffraser 保持一致，传给 hybrid_barbour_matcher）
LEX_MIN_L1_HITS = 1
LEX_MIN_SCORE = 0.70
LEX_MIN_LEAD = 0.05
LEX_REQUIRE_COLOR_EXACT = False


def _to_price(pence: Any) -> Optional[float]:
    try:
        v = float(pence)
    except (TypeError, ValueError):
        return None
    return round(v / 100.0, 2)


def _product_js_url(url: str) -> str:
    """把商品详情页 URL 转换成 Shopify 标准 JSON 接口 URL: .../products/<handle>.js"""
    parts = urlsplit(url)
    path = parts.path
    if not path.endswith(".js"):
        path = path.rstrip("/") + ".js"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _extract_color_from_title(name: str) -> str:
    """标题尾部即颜色 (William Powell 每个颜色是独立商品页), 用已知颜色词表兜底识别多词颜色"""
    words = re.findall(r"[A-Za-z']+", name or "")
    if not words:
        return "No Data"

    lower = [w.lower() for w in words]
    if len(words) >= 2 and (lower[-1] in COLOR_MAP or lower[-2] in COLOR_MAP):
        return normalize_color(" ".join(words[-2:]))
    if lower[-1] in COLOR_MAP:
        return normalize_color(words[-1])
    return words[-1].capitalize()


class WilliamPowellFetcher(BaseFetcher):
    """William Powell 采集器 - requests 抓取 Shopify .js 接口 + hybrid_barbour_matcher 匹配编码"""

    _REQ_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/html,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(self._REQ_HEADERS)

        engine_url = (
            f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
            f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
        )
        self._engine = create_engine(engine_url, pool_size=self.max_workers + 2)

    def _get_dbapi_connection(self, conn: Connection):
        try:
            return conn.connection
        except Exception:
            return conn.connection.connection

    def _fetch_html(self, url: str) -> str:
        """实际抓取的是 Shopify 商品 JSON 接口, 不是渲染后的 HTML"""
        resp = self._session.get(_product_js_url(url), timeout=20)
        resp.raise_for_status()
        return resp.text

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        data = json.loads(html)

        # 1. 基础信息
        name = data.get("title") or "No Data"
        desc_html = data.get("description") or ""
        description = self.clean_description(
            BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
        )
        sku_guess = None  # WP 的 sku (如 "MJC176-RUS-S") 是自家编码, 不是 Barbour 编码, 不能当兜底用

        # 2. 颜色: 标题尾部
        color = _extract_color_from_title(name)

        # 3. 价格 (接口单位为便士)
        current_price = _to_price(data.get("price"))
        original_price = _to_price(data.get("compare_at_price")) or current_price

        # 4. 尺码 + 库存: variants[] 自带 available 布尔值, 无需推断
        size_detail: Dict[str, Dict[str, Any]] = {}
        for v in data.get("variants") or []:
            label = (v.get("title") or v.get("public_title") or v.get("option1") or "").strip()
            if not label:
                continue
            in_stock = bool(v.get("available"))
            size_detail[label] = {
                "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
                "ean": v.get("barcode") or "0000000000000",
            }
        if not size_detail:
            size_detail["One Size"] = {
                "stock_count": DEFAULT_STOCK_COUNT if data.get("available") else 0,
                "ean": "0000000000000",
            }

        # 5. hybrid_barbour_matcher 多级匹配 Product Code (页面本身不显示官方编码)
        with self._engine.begin() as conn:
            raw_conn = self._get_dbapi_connection(conn)
            final_code, _debug_trace = resolve_product_code(
                raw_conn,
                site_name=SITE_NAME,
                url=url,
                scraped_title=name,
                scraped_color=color,
                sku_guess=sku_guess,
                products_table=PRODUCTS_TABLE,
                offers_table=OFFERS_TABLE,
                brand="barbour",
                lex_min_l1_hits=LEX_MIN_L1_HITS,
                lex_min_score=LEX_MIN_SCORE,
                lex_min_lead=LEX_MIN_LEAD,
                lex_require_color_exact=LEX_REQUIRE_COLOR_EXACT,
            )

        # 6. 性别
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=final_code,
            output_format="cn",
        )

        # 7. 尺码行
        product_size, product_size_detail = self.build_size_lines(size_detail, gender)

        return {
            "Product Code": final_code,
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": self.clean_text(color, maxlen=100),
            "Product Price": original_price,
            "Adjusted Price": current_price,
            "Product Material": "No Data",
            "Feature": "No Data",
            "Product Size": product_size,
            "Product Size Detail": product_size_detail,
        }

    def _validate_info(self, info: Dict[str, Any], url: str) -> None:
        required_fields = [
            "Product Code",
            "Product Name",
            "Product Gender",
            "Product Description",
            "Product Size",
            "Product Size Detail",
        ]
        for field in required_fields:
            if field not in info:
                raise ValueError(f"缺失必填字段: {field} (URL: {url})")


def williampowell_fetch_info(max_workers: int = 4):
    """主函数"""
    setup_logging()

    fetcher = WilliamPowellFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=0,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ William Powell 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    williampowell_fetch_info(max_workers=4)
