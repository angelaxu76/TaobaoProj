# -*- coding: utf-8 -*-
"""
Allweathers 采集器 - 重构版 (使用 BaseFetcher)

修复:
- JSON-LD 类型: ProductGroup (Shopify 站点)
- Product Code: 从 hasVariant SKU 提取
- 尺码: 从 hasVariant 提取 (含库存状态)
- 价格: DOM <price-list> 提取 + meta 兜底
- Driver: 每线程独立 (线程安全)
- 新增 Feature / Material 提取
- 字段名: 与 format_txt 对齐 (Product Price / Adjusted Price)

使用方式:
    python -m brands.barbour.supplier.allweathers_fetch_info_v2
"""

from __future__ import annotations

import re
import time
import threading
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

import demjson3

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# 导入通用模块
from common.core.selenium_utils import get_driver, quit_driver

# 配置
from config import BARBOUR, SETTINGS

SITE_NAME = "allweathers"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)


# ================== 辅助函数 ==================

def _extract_name_and_color(soup: BeautifulSoup) -> tuple[str, str]:
    """从 og:title 提取名称和颜色, 格式: 'Name | Color'"""
    og = soup.find("meta", {"property": "og:title"})
    if og and og.get("content"):
        txt = og["content"].strip()
        if "|" in txt:
            name, color = map(str.strip, txt.split("|", 1))
            return name, color
        return txt, "Unknown"

    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        t = t.split("|", 1)[0].strip()
        if "–" in t:
            name, color = map(str.strip, t.split("–", 1))
            return name, color
        return t, "Unknown"

    return "Unknown", "Unknown"


def _extract_description(soup: BeautifulSoup) -> str:
    """提取描述: twitter:description > og:description > JSON-LD"""
    m = soup.find("meta", attrs={"name": "twitter:description"})
    if m and m.get("content"):
        desc = re.sub(r"\s+", " ", m["content"].strip())
        desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
        return desc

    m = soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"):
        return re.sub(r"\s+", " ", m["content"].strip())

    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = re.sub(r"\s+", " ", (j.get("description") or "").strip())
            if desc:
                desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
                return desc
    return "No Data"


def _extract_features(soup: BeautifulSoup) -> str:
    """提取 Key Features"""
    h = soup.find(["h2", "h3"], string=re.compile(r"Key\s*Features", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            items = [re.sub(r"\s+", " ", li.get_text(" ", strip=True)) for li in ul.find_all("li")]
            items = [t for t in items if t]
            if items:
                return " | ".join(items)

    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            if "Key" in desc:
                m = re.search(
                    r"Key\s*Features.*?:\s*(.+?)\s*(Materials\s*&\s*Technical|Frequently|$)",
                    desc, flags=re.I | re.S
                )
                if m:
                    parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"[\r\n]+|•|- ", m.group(1))]
                    parts = [p for p in parts if p]
                    if parts:
                        return " | ".join(parts)
    return "No Data"


def _extract_material_outer(soup: BeautifulSoup) -> str:
    """提取外层材质"""
    h = soup.find(["h2", "h3"], string=re.compile(r"Materials\s*&\s*Technical", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                txt = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
                m = re.match(r"Outer:\s*(.+)", txt, flags=re.I)
                if m:
                    return m.group(1)

    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            m = re.search(r"Outer:\s*(.+)", desc, flags=re.I)
            if m:
                outer = re.sub(r"\s+", " ", m.group(1)).strip()
                outer = re.split(r"[\r\n;]+", outer)[0].strip()
                return outer
    return "No Data"


def _extract_header_price(soup: BeautifulSoup) -> Optional[float]:
    """从 meta product:price:amount 提取价格"""
    m = soup.find("meta", {"property": "product:price:amount"})
    if m and m.get("content"):
        try:
            return float(m["content"])
        except Exception:
            pass
    return None


def _extract_price_pair_from_dom(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
    """
    从 DOM <price-list> 提取 (原价, 现价).
    <sale-price>£现价</sale-price>
    <compare-at-price>£原价</compare-at-price>
    """
    block = soup.find("price-list", class_=re.compile(r"\bprice-list--product\b"))
    if not block:
        return (None, None)

    def _to_float(x: str):
        try:
            return float(re.search(r"([0-9]+(?:\.[0-9]+)?)", x.replace(",", "")).group(1))
        except Exception:
            return None

    sale_el = block.find("sale-price")
    comp_el = block.find("compare-at-price")
    sale = _to_float(sale_el.get_text(" ", strip=True)) if sale_el else None
    comp = _to_float(comp_el.get_text(" ", strip=True)) if comp_el else None

    if sale and comp:
        return (comp, sale)
    if sale and not comp:
        return (sale, sale)
    if comp and not sale:
        return (comp, comp)
    return (None, None)


# ================== 采集器实现 ==================

class AllweathersFetcher(BaseFetcher):
    """
    Allweathers 采集器

    重写:
    - parse_detail_page: 与 v1 逻辑对齐
    - _fetch_html: 每线程独立 driver (线程安全)
    """

    def _fetch_html(self, url: str) -> str:
        """
        覆盖基类: 每线程独立 driver, 避免多线程冲突.
        driver name 使用 site_name + thread id 保证唯一.
        """
        tid = threading.current_thread().ident
        driver_name = f"{self.site_name}_{tid}"
        driver = get_driver(
            name=driver_name,
            headless=self.headless,
            window_size="1920,1080",
        )
        try:
            driver.get(url)
            time.sleep(self.wait_seconds)
            return driver.page_source
        finally:
            quit_driver(driver_name)

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析 Allweathers 商品详情页 - 与 v1 逻辑完全对齐
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 名称 & 颜色 (og:title)
        name, color = _extract_name_and_color(soup)

        # 2. JSON-LD (Shopify 用 ProductGroup)
        jsonld = None
        for s in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                j = demjson3.decode(s.string)
            except Exception:
                continue
            if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
                jsonld = j
                break

        if not jsonld:
            raise ValueError("未找到 JSON-LD 数据段")

        # 3. 从 hasVariant 提取尺码/库存/Product Code
        variants = jsonld.get("hasVariant", [])
        if not variants:
            raise ValueError("❌ 未找到尺码变体")

        first_sku = (variants[0].get("sku") or "")
        base_sku = first_sku.split("-")[0] if first_sku else "Unknown"

        size_detail = {}
        for item in variants:
            sku = item.get("sku", "")
            offer = item.get("offers") or {}
            availability = (offer.get("availability") or "").lower()
            can_order = "instock" in availability
            size_tail = sku.split("-")[-1] if "-" in sku else "Unknown"
            size = f"UK {re.sub(r'\\s+', ' ', size_tail)}"
            size_detail[size] = {
                "stock_count": DEFAULT_STOCK_COUNT if can_order else 0,
                "ean": "0000000000000",
            }

        # 4. 性别 (中文, 与 format_txt / size_normalizer 一致)
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=base_sku,
            output_format="cn",
        )

        # 5. 描述 / 特性 / 材质
        description = _extract_description(soup)
        features = _extract_features(soup)
        material_outer = _extract_material_outer(soup)

        # 6. 价格: DOM 成对价优先, meta 兜底
        price_header = _extract_header_price(soup)
        orig, curr = _extract_price_pair_from_dom(soup)
        original_price = orig or price_header
        current_price = curr or price_header

        # 7. 尺码行 (用基类工具)
        ps, psd = self.build_size_lines(size_detail, gender)

        # 8. 返回 - 字段名与 format_txt 对齐
        return {
            "Product Code": base_sku,
            "Product Name": name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": original_price,
            "Adjusted Price": current_price,
            "Product Material": material_outer,
            "Feature": features,
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

def allweathers_fetch_info(
    max_workers: int = 6,
    headless: bool = False,
):
    """
    主函数 - 兼容旧版接口
    """
    setup_logging()

    fetcher = AllweathersFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=2.5,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Allweathers 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    allweathers_fetch_info(max_workers=6, headless=False)
