# -*- coding: utf-8 -*-
"""
Barbour 官网采集器 - 重构版

对比:
- 旧版: 339 行
- 新版: ~110 行
- 代码减少: 68%

特点:
- 使用 requests (不是 Selenium) - HTTP请求更快
- JSON-LD 提取名称和 SKU
- 尺码按钮的 disabled 状态判断库存
"""

from __future__ import annotations

import re
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
import requests

from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from config import BARBOUR

SITE_NAME = "barbour"
LINKS_FILE = BARBOUR["LINKS_FILES"]["barbour"]
OUTPUT_DIR = BARBOUR["TXT_DIRS"]["barbour"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


class BarbourFetcher(BaseFetcher):
    """
    Barbour 官网采集器

    特点:
    - 使用 requests 而非 Selenium (更快)
    - 从 JSON-LD 提取名称和 SKU
    - 通过按钮的 disabled 状态判断库存
    """

    def _fetch_html(self, url: str) -> str:
        """
        覆盖基类方法 - Barbour 官网使用 requests (不需要 Selenium)
        """
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"HTTP请求失败: {url} - {e}")
            raise

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        Barbour 官网特定解析逻辑
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 从 JSON-LD 提取名称和 SKU
        jsonld = self.extract_jsonld(soup, "Product") or {}
        name = jsonld.get("name", "No Data")
        sku = jsonld.get("sku", "No Data")

        # 2. 提取描述
        desc_tag = soup.find("div", {"id": "collapsible-description-1"})
        description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else "No Data"

        # 去除描述中的 SKU
        if sku and sku != "No Data":
            description = description.replace(f"SKU: {sku}", "").strip() or "No Data"

        # 3. 提取价格 (Barbour 官网特定: span.sales span.value[content])
        price_tag = soup.select_one("span.sales span.value")
        price = None
        if price_tag and price_tag.has_attr("content"):
            price = self.parse_price(price_tag["content"])

        # 4. 提取颜色 (span.selected-color)
        color_tag = soup.select_one("span.selected-color")
        color = "No Data"
        if color_tag:
            color = color_tag.get_text(strip=True).replace("(", "").replace(")", "")

        # 5. 提取尺码和库存状态 (Barbour 特有: button.size-button + disabled 状态)
        size_detail = self._extract_sizes_with_stock(soup)

        # 6. 从 HTML 提取性别 (item_category 字段)
        gender = self._extract_gender_from_html(html)

        # 7. 使用 SKU 作为 Product Code
        product_code = sku

        # 8. 格式化尺码
        product_size, product_size_detail = self.build_size_lines(size_detail, gender)

        # 9. 提取 Care & Product Information
        feature = self._extract_features(soup)

        # 10. 返回标准化字典
        price_str = f"{price:.2f}" if price else "0"
        return {
            "Product Code": product_code,
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Color": self.clean_text(color, maxlen=100),
            "Product Gender": self._convert_gender_to_english(gender),
            "Product Description": self.clean_description(description),
            "Feature": feature,
            "Product Price": price_str,       # txt_writer / DB 导入使用此 key
            "Adjusted Price": price_str,      # txt_writer / DB 导入使用此 key
            "Original Price (GBP)": price_str,   # BaseFetcher._validate_info 要求
            "Discount Price (GBP)": "No Data",   # BaseFetcher._validate_info 要求
            "Product Size": product_size,
            "Product Size Detail": product_size_detail,
        }

    # ========== Barbour 特有方法 ==========

    def _extract_sizes_with_stock(self, soup: BeautifulSoup) -> Dict[str, Dict]:
        """
        Barbour 特有: 从尺码元素提取尺码和库存状态

        新版页面结构（2024+）:
        <span class="size-button text-center selectable"   data-attr-value="8">8</span>  # 有货
        <span class="size-button text-center unselectable" data-attr-value="10">10</span> # 无货
        """
        size_detail = {}

        # 新结构：span.size-button（旧版是 button.size-button，已不再出现）
        size_spans = soup.select("span.size-button[data-attr-value]")
        for span in size_spans:
            size_text = span.get("data-attr-value", "").strip() or span.get_text(strip=True)
            if not size_text:
                continue

            classes = span.get("class") or []
            # unselectable = 缺货；selectable = 有货
            disabled = "unselectable" in classes or "not-available" in classes
            stock_count = 0 if disabled else self.default_stock

            size_detail[size_text] = {
                "stock_count": stock_count,
                "ean": "0000000000000",
            }

        return size_detail

    def _extract_gender_from_html(self, html: str) -> str:
        """
        Barbour 特有: 从 HTML 中的 item_category 字段提取性别

        示例: "item_category": "Womens"
        """
        m = re.search(r'"item_category"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
        gender_raw = m.group(1).strip().lower() if m else ""

        mapping = {
            "womens": "女款",
            "women": "女款",
            "ladies": "女款",
            "mens": "男款",
            "men": "男款",
            "kids": "童款",
            "children": "童款",
            "child": "童款",
            "unisex": "中性",
        }

        return mapping.get(gender_raw, "未知")

    def _extract_features(self, soup: BeautifulSoup) -> str:
        """
        提取 Care & Product Information 内容。

        页面结构：
          <div class="container-accordion-pdp vertical-acoordion js-modal-button">
            <button>View Care & Product Information</button>
            <div class="hidden-modal-body">
              Care & Information
              Outer: 100% Polyamide
              Inner: 100% Polyester
              ...
            </div>
          </div>
        """
        for btn in soup.find_all("button", class_="pdp-dd-vertical-accordion"):
            if "care" not in btn.get_text(strip=True).lower():
                continue
            body = btn.find_next_sibling("div", class_="hidden-modal-body")
            if not body:
                continue
            lines = [
                ln.strip()
                for ln in body.get_text(separator="\n", strip=True).splitlines()
                if ln.strip() and ln.strip().lower() not in {"care & information", "care &amp; information"}
            ]
            return " | ".join(lines) if lines else "No Data"
        return "No Data"

    def _convert_gender_to_english(self, gender_cn: str) -> str:
        """转换中文性别为英文"""
        mapping = {
            "女款": "Women",
            "男款": "Men",
            "童款": "Kids",
            "中性": "Unisex",
            "未知": "No Data",
        }
        return mapping.get(gender_cn, "No Data")


# ================== 主入口 ==================

def barbour_fetch_info(
    max_workers: int = 8,
    headless: bool = False,  # 不使用，保留向后兼容
):
    """
    主函数 - 兼容旧版接口
    """
    setup_logging()

    fetcher = BarbourFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=0,  # requests 不需要等待
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Barbour 官网抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    barbour_fetch_info(max_workers=8, headless=False)
