# -*- coding: utf-8 -*-
"""
Outdoor & Country 采集器 - 重构版 (使用 BaseFetcher)

基于 outdoorandcountry_fetch_info_v2.py 重构
特点:
- span.price-sales 价格
- button.size-variant 尺码
- MPN 字段获取编码
- 需要 parse_offer_info 辅助模块

对比:
- 旧版 (outdoorandcountry_fetch_info_v2.py): 442 行
- 新版 (本文件): ~150 行
- 代码减少: 66%

使用方式:
    python -m brands.barbour.supplier.outdoorandcountry_fetch_info_v3
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any
from bs4 import BeautifulSoup

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# 导入站点特定的解析模块
from brands.barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# 配置
from config import BARBOUR, SETTINGS

SITE_NAME = "outdoorandcountry"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)


# ================== 采集器实现 ==================

class OutdoorAndCountryFetcher(BaseFetcher):
    """
    Outdoor & Country 采集器

    特点:
    - 使用 parse_offer_info 解析 offers (尺码/库存/价格)
    - 从 JSON-LD 提取 Product Code
    - MPN 字段优先
    """

    # 尺码排序规则
    WOMEN_NUM = ["6", "8", "10", "12", "14", "16", "18", "20"]
    MEN_ALPHA = ["S", "M", "L", "XL", "XXL", "XXXL"]
    MEN_NUM = [str(s) for s in range(32, 52, 2)]

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析 Outdoor & Country 商品详情页

        页面特点:
        - parse_offer_info 提供基础信息
        - JSON-LD 的 MPN 字段包含编码
        - 需要从 URL 提取颜色
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 使用站点特定解析器获取基础信息
        info = parse_offer_info(html, url, site_name=SITE_NAME) or {}

        # 2. 提取名称
        name = info.get("Product Name", "No Data")

        # 3. 提取颜色 (从 URL 或解析结果)
        color = info.get("Product Color") or self._normalize_color_from_url(url)

        # 4. 提取描述
        description = self._extract_description(html)

        # 5. 提取特征
        features = self._extract_features(html)

        # 6. 提取 Product Code (从 JSON-LD MPN)
        product_code = info.get("Product Color Code") or self._extract_color_code_from_jsonld(html)

        # 7. 推断性别
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=product_code,
            output_format="zh",  # 中文输出
        )

        # 8. 格式化尺码 (从 offers)
        offers = info.get("Offers", [])
        product_size_detail = self._build_sizes_from_offers(offers, gender)

        # 9. 提取价格
        original_price = info.get("original_price_gbp", "No Data")
        discount_price = info.get("discount_price_gbp", "No Data")

        # 10. 返回标准化字典
        return {
            "Product Code": product_code or "No Data",
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Color": self.clean_text(color, maxlen=100),
            "Product Gender": gender,
            "Product Description": self.clean_description(description),
            "Original Price (GBP)": original_price,
            "Discount Price (GBP)": discount_price,
            "Product Size": "No Data",  # 旧版未使用此字段
            "Product Size Detail": product_size_detail,
            "Feature": features,
        }

    def _normalize_color_from_url(self, url: str) -> str:
        """从 URL 参数提取颜色 (?c=xxx)"""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            qs = parse_qs(urlparse(url).query)
            c = qs.get("c", [None])[0]
            if not c:
                return ""
            c = unquote(c)
            c = c.replace("\\", "/")
            c = re.sub(r"\s*/\s*", " / ", c)
            c = re.sub(r"\s+", " ", c).strip()
            c = " ".join(w.capitalize() for w in c.split(" "))
            return c
        except Exception:
            return ""

    def _extract_description(self, html: str) -> str:
        """提取商品描述"""
        soup = BeautifulSoup(html, "html.parser")

        # 优先 og:description
        tag = soup.find("meta", attrs={"property": "og:description"})
        if tag and tag.get("content"):
            desc = tag["content"]
            desc = desc.replace("<br>", "").replace("<br/>", "").replace("<br />", "")
            return desc.strip()

        # 兜底: product_tabs
        tab = soup.select_one(".product_tabs .tab_content[data-id='0'] div")
        if tab:
            return tab.get_text(" ", strip=True)

        return "No Data"

    def _extract_features(self, html: str) -> str:
        """提取产品特征列表"""
        soup = BeautifulSoup(html, "html.parser")

        h3 = soup.find("h3", attrs={"title": "Features"})
        if h3:
            ul = h3.find_next("ul")
            if ul:
                items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                return "; ".join(items)

        return "No Data"

    def _extract_color_code_from_jsonld(self, html: str) -> str:
        """从 JSON-LD 的 MPN 字段提取 Barbour Product Code"""
        import json
        soup = BeautifulSoup(html, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = (script.string or "").strip()
                if not raw:
                    continue

                j = json.loads(raw)
                candidates = j if isinstance(j, list) else [j]

                for obj in candidates:
                    if not isinstance(obj, dict) or obj.get("@type") != "Product":
                        continue

                    offers = obj.get("offers")
                    if not offers:
                        continue

                    offers_list = offers if isinstance(offers, list) else [offers]

                    for off in offers_list:
                        mpn = (off or {}).get("mpn")
                        if not isinstance(mpn, str):
                            continue

                        # MPN 格式: "MCA0538NY71_34"
                        mpn = mpn.split("_")[0].strip()

                        # 提取前 11 位作为 Product Code
                        if len(mpn) >= 11:
                            maybe_code = mpn[:11]
                            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2}$", maybe_code):
                                return maybe_code

            except Exception:
                continue

        return ""

    def _build_sizes_from_offers(self, offers, gender: str):
        """从 offers 构建 Product Size Detail"""
        if not offers:
            return "No Data"

        temp = []
        for size, price, stock_text, can_order in offers:
            size = (size or "").strip()
            if not size:
                continue

            # 判断库存
            stock = 0
            if (stock_text or "").strip() in ("有货", "In Stock", "available"):
                stock = DEFAULT_STOCK_COUNT
            if can_order and stock == 0:
                stock = DEFAULT_STOCK_COUNT

            # 清理尺码
            cs = self._clean_size(size)
            if not cs:
                continue

            # 过滤超大尺码 (>=52)
            m = re.match(r"^(\d{2})$", cs)
            if m and int(m.group(1)) >= 52:
                continue

            temp.append((cs, stock))

        if not temp:
            return "No Data"

        # 去重 (保留最大库存)
        bucket = {}
        for s, stock in temp:
            bucket[s] = max(bucket.get(s, 0), stock)

        # 排序
        ordered = []
        if "女" in (gender or ""):
            # 女款: 数字优先
            for s in self.WOMEN_NUM:
                if s in bucket:
                    ordered.append(s)
            for s in bucket:
                if s not in ordered:
                    ordered.append(s)
        else:
            # 男款: 字母 + 数字
            for s in self.MEN_ALPHA:
                if s in bucket:
                    ordered.append(s)
            for s in self.MEN_NUM:
                if s in bucket:
                    ordered.append(s)
            for s in bucket:
                if s not in ordered:
                    ordered.append(s)

        # 格式化
        out = []
        for s in ordered:
            qty = DEFAULT_STOCK_COUNT if bucket.get(s, 0) > 0 else 0
            out.append(f"{s}:{qty}:0000000000000")

        return ";".join(out) if out else "No Data"

    def _clean_size(self, raw: str) -> str:
        """清理尺码"""
        from common_taobao.core.size_utils import clean_size_for_barbour

        raw = (raw or "").strip()
        if not raw:
            return ""

        s = clean_size_for_barbour(raw) or raw
        return s.strip()


# ================== 主入口 ==================

def outdoorandcountry_fetch_info(
    max_workers: int = 2,
    headless: bool = True,
):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数 (建议 2, Outdoor 强风控)
        headless: 是否无头模式
    """
    setup_logging()

    fetcher = OutdoorAndCountryFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=2.0,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Outdoor & Country 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    outdoorandcountry_fetch_info(max_workers=2, headless=True)
