# -*- coding: utf-8 -*-
"""
CHO (Country House Outdoor) 采集器 - 重构版

修复:
- JSON-LD: 用 demjson3 解析 (兼容 Shopify 非标 JSON)
- 尺码/颜色: 从 hasVariant name 解析 (格式: "Name - Color / Size")
- 价格: DOM .price__sale / .price__regular 提取
- Driver: 每线程独立 (线程安全)
- 字段名: 与 format_txt 对齐 (Product Price / Adjusted Price)
- 性别: 中文输出 (男款/女款)

使用方式:
    python -m brands.barbour.supplier.cho_fetch_info_v2
"""

from __future__ import annotations

import re
import time
from typing import Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
import psycopg2
import demjson3

from brands.barbour.core.hybrid_barbour_matcher import resolve_product_code

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# 导入通用模块
from common.browser.selenium_utils import get_driver

# 配置
from config import BARBOUR, SETTINGS, PGSQL_CONFIG

SITE_NAME = "cho"
LINKS_FILE = BARBOUR["LINKS_FILES"].get("cho", "")
OUTPUT_DIR = BARBOUR["TXT_DIRS"].get("cho", "")
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# 判断编码是否为完整 11 位格式 (如 LQU0475OL71)
_FULL_CODE_RE = re.compile(r"^[A-Z]{2,3}\d{4}[A-Z]{2}\d{2}$")


def _is_partial_code(code: str) -> bool:
    """判断编码是否为截断格式 (7位, 如 LQU0475, 无颜色后缀)"""
    if not code or code == "No Data":
        return False
    return len(code) <= 8 and not _FULL_CODE_RE.match(code)


# ================== 辅助函数 ==================

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _to_float(x: str) -> Optional[float]:
    if not x:
        return None
    try:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", x.replace(",", ""))
        return float(m.group(1)) if m else None
    except Exception:
        return None


def _extract_price_pair_from_dom_cho(soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
    """
    从 CHO DOM 中抓取 (original_price, current_price)
    - 打折:
        .price__sale .price-item--sale        => 现价
        .savings-price .price-item--regular   => 原价
    - 无打折:
        .price__regular .price-item--regular  => 原价 == 现价
    """
    sale_span = soup.select_one(".price__sale .price-item--sale")
    was_span = soup.select_one(".price__sale .savings-price .price-item--regular")
    sale_price = _to_float(sale_span.get_text(" ", strip=True)) if sale_span else None
    was_price = _to_float(was_span.get_text(" ", strip=True)) if was_span else None

    if sale_price is not None and was_price is not None:
        return was_price, sale_price  # (原价, 折后价)

    reg_span = soup.select_one(".price__regular .price-item--regular")
    reg_price = _to_float(reg_span.get_text(" ", strip=True)) if reg_span else None
    if reg_price is not None:
        return reg_price, reg_price

    return None, None


def _load_product_jsonld(soup: BeautifulSoup) -> dict:
    """返回 JSON-LD 中的 ProductGroup / Product 节点 (用 demjson3 兼容非标 JSON)"""
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        txt = (tag.string or tag.text or "").strip()
        if not txt:
            continue
        try:
            j = demjson3.decode(txt)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            return j
    raise ValueError("未找到 ProductGroup/Product JSON-LD 数据")


def _extract_code_from_description(desc: str) -> str:
    """
    从 description 末尾提取 Barbour 编码.
    完整格式: MQU0281NY71 (11字符: 3字母+4数字+2字母+2数字)
    截断格式: LCA0362     (7字符: 3字母+4数字, CHO 常见)
    优先匹配完整格式, 其次匹配截断格式.
    """
    if not desc:
        return "No Data"

    # 正则: 完整 11 字符格式
    FULL_PAT = r"\b[A-Z]{2,3}\d{4}[A-Z]{2}\d{2}\b"
    # 正则: 截断 7 字符格式 (CHO 常用, 无颜色后缀)
    SHORT_PAT = r"\b[A-Z]{2,3}\d{4}\b"

    lines = [l.strip() for l in desc.splitlines() if l.strip()]

    # 1) 先在最后一行找完整格式
    if lines:
        last = lines[-1]
        m = re.search(FULL_PAT, last)
        if m:
            return m.group(0)

    # 2) 全文找完整格式 (取最后一个)
    m_all = list(re.finditer(FULL_PAT, desc))
    if m_all:
        return m_all[-1].group(0)

    # 3) 最后一行找截断格式
    if lines:
        last = lines[-1]
        m = re.search(SHORT_PAT, last)
        if m:
            return m.group(0)

    # 4) 全文找截断格式 (取最后一个)
    m_all = list(re.finditer(SHORT_PAT, desc))
    if m_all:
        return m_all[-1].group(0)

    return "No Data"


def _strip_code_from_description(desc: str, code: str) -> str:
    if not desc:
        return "No Data"
    if not code or code == "No Data":
        return _clean_text(desc)
    return _clean_text(desc.replace(code, "")).strip(" -–|,")


# ================== 采集器实现 ==================

class CHOFetcher(BaseFetcher):
    """
    CHO 采集器 - 与 v1 逻辑完全对齐

    重写:
    - parse_detail_page: 从 hasVariant 解析尺码/颜色, DOM 解析价格
    - _fetch_html: 每线程独立 driver
    - 截断编码自动通过 DB 匹配补全
    """

    

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._db_conn = None

    def _get_db_conn(self):
        """懒加载 DB 连接 (用于 partial_code 查询)"""
        if self._db_conn is None or self._db_conn.closed:
            try:
                self._db_conn = psycopg2.connect(**PGSQL_CONFIG)
                self.logger.info("🔗 DB 连接已建立 (用于编码补全)")
            except Exception as e:
                self.logger.warning(f"DB 连接失败, 跳过编码补全: {e}")
                return None
        return self._db_conn

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """解析 CHO 商品详情页 - 与 v1 逻辑完全对齐"""
        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD (ProductGroup)
        data = _load_product_jsonld(soup)
        name = data.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
        desc = data.get("description") or ""
        desc = desc.replace("\\n", "\n")
        desc = desc.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

        # 2. Product Code (从 description 末尾提取)
        product_code = _extract_code_from_description(desc)
        description = _strip_code_from_description(desc, product_code)

        # 3. 从 hasVariant 提取尺码/颜色/库存
        variants = data.get("hasVariant", [])
        if isinstance(variants, dict):
            variants = [variants]
        if not variants:
            raise ValueError("未找到 hasVariant 变体数据")

        size_detail = {}
        color = "No Data"

        for v in variants:
            v_name = v.get("name") or ""
            # name 形如: Barbour Powell Mens Quilted Jacket - Navy - Navy / L
            tail = v_name.split(" - ")[-1] if " - " in v_name else v_name
            if " / " in tail:
                c_txt, sz_txt = [p.strip() for p in tail.split(" / ", 1)]
            else:
                c_txt, sz_txt = (tail.strip() or "No Data"), "Unknown"
            if color == "No Data":
                color = c_txt or "No Data"

            offers = v.get("offers") or {}
            avail = (offers.get("availability") or "").lower()
            in_stock = "instock" in avail

            size_detail[sz_txt] = {
                "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
                "ean": v.get("gtin") or v.get("sku") or "0000000000000",
            }

        # 3.5 截断编码补全: 如 LQU0475 → 查 DB 匹配颜色 → LQU0475OL71
        if _is_partial_code(product_code):
            conn = self._get_db_conn()
            if conn:
                try:
                    full_code, trace = resolve_product_code(
                        conn,
                        site_name=SITE_NAME,
                        url=url,
                        scraped_title=name,
                        scraped_color=color,
                        sku_guess=product_code,
                        partial_code=product_code,
                    )
                    if full_code and full_code != "No Data":
                        self.logger.info(
                            f"🔗 编码补全: {product_code} → {full_code} "
                            f"(by={trace.get('final', {}).get('by', '?')})"
                        )
                        product_code = full_code
                except Exception as e:
                    self.logger.warning(f"编码补全失败 ({product_code}): {e}")

        # 4. 性别 (中文, 与 size_normalizer / format_txt 一致)
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=product_code,
            output_format="cn",
        )

        # 5. 价格: DOM 优先
        original_price, current_price = _extract_price_pair_from_dom_cho(soup)

        # 6. 尺码行
        ps, psd = self.build_size_lines(size_detail, gender)

        # 7. 返回 - 字段名与 format_txt 对齐
        return {
            "Product Code": product_code or "No Data",
            "Product Name": name,
            "Product Description": description or "No Data",
            "Product Gender": gender,
            "Product Color": color or "No Data",
            "Product Price": original_price,
            "Adjusted Price": current_price,
            "Product Material": "No Data",
            "Feature": "No Data",
            "Product Size": ps,
            "Product Size Detail": psd,
        }

    def _validate_info(self, info: Dict[str, Any], url: str) -> None:
        """覆盖基类: 使用与 v1 一致的字段名验证"""
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


# ================== 主入口 ==================

def cho_fetch_info(
    max_workers: int = 4,
    headless: bool = False,
):
    """主函数 - 兼容旧版接口"""
    setup_logging()

    fetcher = CHOFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=2.5,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ CHO 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    cho_fetch_info(max_workers=4, headless=False)
