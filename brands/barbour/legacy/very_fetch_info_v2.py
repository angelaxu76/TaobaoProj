# -*- coding: utf-8 -*-
"""
Very 采集器 - 重构版

对比:
- 旧版: 533 行
- 新版: ~150 行
- 代码减少: 72%

特点:
- 从 JSON initial_state 提取数据
- 尺码和库存从 skus[].stock.code 判断
- 价格从 price.amount.decimal/previous 提取
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from bs4 import BeautifulSoup

from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from config import BARBOUR

SITE_NAME = "very"
LINKS_FILE = BARBOUR["LINKS_FILES"].get("very", "")
OUTPUT_DIR = BARBOUR["TXT_DIRS"].get("very", "")


class VeryFetcher(BaseFetcher):
    """
    Very 采集器

    特点:
    - JSON initial_state 数据结构
    - skus[] 数组包含尺码和库存信息
    - price.amount.decimal/previous 价格结构
    """

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        Very 特定解析逻辑
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 提取 JSON initial_state (Very 特有)
        initial_state = self._extract_initial_state(html)
        product_data = initial_state.get("productData") if initial_state else None

        # 2. 提取名称
        name = "No Data"
        if product_data:
            name = product_data.get("name", "No Data")
        if name == "No Data":
            og_title = self.extract_og(soup, "title")
            if og_title:
                name = og_title

        # 3. 提取颜色 (Very 特有: productData.colour)
        color = self._extract_color(product_data, soup)

        # 4. 提取价格 (Very 特有: price.amount.decimal/previous)
        current_price, original_price = self._extract_prices(initial_state, soup)

        # 5. 提取描述
        description = "No Data"
        if product_data:
            desc = product_data.get("description", "")
            if desc:
                description = self.clean_description(desc)

        # 6. 提取尺码和库存 (Very 特有: skus[].stock.code)
        size_detail = self._extract_sizes_and_stock(initial_state, soup)

        # 7. 推断性别 (从标题和 category/department)
        gender = self._extract_gender(name, product_data)

        # 8. 提取 Product Code (从描述或使用 productID)
        product_code = self.extract_barbour_code(description) or "No Data"
        if product_code == "No Data" and product_data:
            product_id = product_data.get("productId", "")
            if product_id:
                product_code = str(product_id)

        # 9. 格式化尺码
        product_size, product_size_detail = self.build_size_lines(size_detail, gender)

        # 10. 返回标准化字典
        return {
            "Product Code": product_code,
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Color": self.clean_text(color, maxlen=100),
            "Product Gender": gender,
            "Product Description": description,
            "Original Price (GBP)": f"{original_price:.2f}" if original_price else "No Data",
            "Discount Price (GBP)": f"{current_price:.2f}" if current_price and current_price < (original_price or 9999) else "No Data",
            "Product Size": product_size,
            "Product Size Detail": product_size_detail,
        }

    # ========== Very 特有方法 ==========

    def _extract_initial_state(self, html: str) -> Optional[Dict]:
        """
        Very 特有: 提取 JSON initial_state

        格式: <script>window.__INITIAL_STATE__ = {...}</script>
        """
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return None

    def _extract_color(self, product_data: Optional[Dict], soup: BeautifulSoup) -> str:
        """
        Very 特有: 从 productData.colour 或 meta 标签提取颜色
        """
        if product_data:
            color = product_data.get("colour") or product_data.get("color")
            if color:
                return self.clean_text(str(color), maxlen=100)

        # 兜底: meta 标签
        color_meta = soup.find("meta", attrs={"property": "product:color"})
        if color_meta and color_meta.get("content"):
            return self.clean_text(color_meta["content"], maxlen=100)

        return "No Data"

    def _extract_prices(
        self,
        initial_state: Optional[Dict],
        soup: BeautifulSoup,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Very 特有: 从 price.amount.decimal/previous 提取价格

        返回: (current_price, original_price)
        """
        if initial_state:
            price = (initial_state.get("price") or {}).get("amount") or {}
            current = self._to_num(price.get("decimal") or price.get("current"))
            original = self._to_num(price.get("previous")) or current

            if current is not None:
                return current, (original if original is not None else current)

        # 兜底: meta 标签
        price_meta = soup.find("meta", attrs={"property": "product:price:amount"})
        if price_meta and price_meta.get("content"):
            price = self._to_num(price_meta["content"])
            return price, price

        return None, None

    def _extract_sizes_and_stock(
        self,
        initial_state: Optional[Dict],
        soup: BeautifulSoup,
    ) -> Dict[str, Dict]:
        """
        Very 特有: 从 skus[] 数组提取尺码和库存

        stock.code: "DCSTOCK" / "IN_STOCK" / "AVAILABLE" = 有货
        """
        size_detail = {}

        # 1. 优先从 JSON skus[] 提取
        if initial_state and isinstance(initial_state.get("skus"), list):
            for sku in initial_state["skus"]:
                opts = sku.get("options") or {}
                size = str(opts.get("size") or "").strip()
                if not size:
                    continue

                stock_code = (sku.get("stock") or {}).get("code") or ""
                stock_count = 0

                if stock_code and stock_code.upper() in {"DCSTOCK", "IN_STOCK", "AVAILABLE"}:
                    stock_count = self.default_stock

                size_detail[size] = {
                    "stock_count": stock_count,
                    "ean": "",
                }

        # 2. 兜底: DOM checkbox
        if not size_detail:
            for inp in soup.select('input[id^="size-"][type="checkbox"]'):
                size = (inp.get("id") or "").replace("size-", "").strip()
                if not size:
                    continue

                disabled = inp.has_attr("disabled") or inp.get("aria-disabled") == "true"
                stock_count = 0 if disabled else self.default_stock

                size_detail[size] = {
                    "stock_count": stock_count,
                    "ean": "",
                }

        return size_detail

    def _extract_gender(self, title: str, product_data: Optional[Dict]) -> str:
        """
        Very 特有: 从标题和 category/department 推断性别
        """
        # 从标题
        t = (title or "").lower()
        if "women" in t or "ladies" in t:
            return "Women"
        if "men" in t and "women" not in t:
            return "Men"

        # 从 product_data
        if product_data:
            dept = (
                (product_data.get("subcategory") or "") +
                " " +
                (product_data.get("category") or "") +
                " " +
                (product_data.get("department") or "")
            )
            d = dept.lower()

            if any(k in d for k in ["ladies", "women", "women's"]):
                return "Women"
            if "men" in d and "women" not in d:
                return "Men"

        return "No Data"

    def _to_num(self, s: Optional[str]) -> Optional[float]:
        """转换字符串为数字"""
        if s is None:
            return None

        m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", str(s).replace(",", ""))
        return float(m.group(1)) if m else None


# ================== 主入口 ==================

def very_fetch_info(
    max_workers: int = 4,
    headless: bool = False,
):
    """
    主函数 - 兼容旧版接口
    """
    setup_logging()

    fetcher = VeryFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=2.0,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Very 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    very_fetch_info(max_workers=4, headless=False)
