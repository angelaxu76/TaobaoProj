# -*- coding: utf-8 -*-
"""
Magrigg (Griggs / magrigg.co.uk) 采集器

站点特点 (Magento 2):
- 用普通 requests + 浏览器 UA 即可访问, 无需 Selenium
- Product Code 藏在 JSON-LD Product.description 末尾:
    "...Tailored Fit\n\nProduct Code - MQU0240NY92"
  与可见 DOM (.product_desc_content__short-desc) 中的文案完全一致
- 原价/折后价 与 尺码库存 不在 JSON-LD 里, 在页面内嵌的
  text/x-magento-init 脚本块 "spConfig" JSON 中:
    spConfig.prices.{oldPrice,finalPrice}.amount
    spConfig.attributes["<id>"].options[].{label, products}
  (products 为空数组 = 该尺码无货/不可选)
- 页面没有颜色 swatch, 每个颜色是独立 URL/独立商品, 颜色需从标题尾部解析

使用方式:
    python -m brands.barbour.supplier.magrigg_fetch_info
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from brands.barbour.core.color_utils import COLOR_MAP, normalize_color

from config import BARBOUR, SETTINGS

SITE_NAME = "magrigg"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

_CODE_RE = re.compile(r"Product Code\s*-\s*([A-Z]{2,3}\d{4}[A-Z]{2}\d{2})", re.IGNORECASE)
_FULL_CODE_RE = re.compile(r"^[A-Z]{2,3}\d{4}[A-Z]{2}\d{2}$")


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _extract_balanced_json(text: str, key: str) -> Optional[dict]:
    """从 text/x-magento-init 脚本的大 JS 对象里, 抠出 "key": {...} 对应的合法 JSON 子串并解析"""
    marker = f'"{key}":'
    idx = text.find(marker)
    if idx == -1:
        return None
    start = text.find("{", idx + len(marker))
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _load_product_jsonld(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        raw = (tag.string or tag.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    raise ValueError("未找到 Product JSON-LD 数据")


def _extract_code_from_dom(soup: BeautifulSoup) -> Optional[str]:
    """
    主要来源: 页面上独立展示的 "Code: XXXXXXXXXXX" 属性块
        <div class="product attribute product-code">
            <strong class="type">Code:</strong>
            <div class="value">MSH5048TN11</div>
        </div>
    比 description 末尾文案更可靠 (不少商品 description 里根本不带编码, 如衬衫类)
    """
    el = soup.select_one("div.product-code .value")
    if not el:
        return None
    code = el.get_text(strip=True).upper()
    return code if _FULL_CODE_RE.match(code) else None


def _extract_code_from_description(desc: str) -> Optional[str]:
    """兜底来源: description 末尾的 "Product Code - XXXXXXXXXXX" 文案"""
    m = _CODE_RE.search(desc or "")
    return m.group(1).upper() if m else None


def _clean_description(desc: str, code: str) -> str:
    """从 description 里去掉 "Product Code - XXX" 这一行 (若存在), 其余按空白清洗"""
    if not desc:
        return "No Data"

    cleaned = desc
    if code and code != "No Data":
        m = re.search(rf"Product Code\s*-\s*{re.escape(code)}", desc, re.IGNORECASE)
        if m:
            cleaned = desc[: m.start()]

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–|,\n\r")
    return cleaned or "No Data"


def _extract_color_from_title(name: str) -> str:
    """标题尾部即颜色 (页面无颜色下拉框, 每个颜色是独立 URL), 用已知颜色词表兜底识别多词颜色"""
    words = re.findall(r"[A-Za-z']+", name or "")
    if not words:
        return "No Data"

    lower = [w.lower() for w in words]
    if len(words) >= 2 and (lower[-1] in COLOR_MAP or lower[-2] in COLOR_MAP):
        return normalize_color(" ".join(words[-2:]))
    if lower[-1] in COLOR_MAP:
        return normalize_color(words[-1])
    return words[-1].capitalize()


class MagriggFetcher(BaseFetcher):
    """Magrigg 采集器 - requests 抓取 + JSON-LD/spConfig 解析"""

    _REQ_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(self._REQ_HEADERS)

    def _fetch_html(self, url: str) -> str:
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD: 商品名 + 描述
        data = _load_product_jsonld(soup)
        name = data.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
        raw_desc = (data.get("description") or "").replace("\\n", "\n")

        # 1.5 Product Code: 优先取页面独立的 "Code:" 属性块, 不存在再退回 description 文案
        product_code = (
            _extract_code_from_dom(soup)
            or _extract_code_from_description(raw_desc)
            or "No Data"
        )
        description = _clean_description(raw_desc, product_code)

        # 2. 颜色: 标题尾部
        color = _extract_color_from_title(name)

        # 3. 性别
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=product_code,
            output_format="cn",
        )

        # 4. spConfig: 价格 + 尺码库存
        sp_config = _extract_balanced_json(html, "spConfig")

        original_price: Optional[float] = None
        current_price: Optional[float] = None
        size_detail: Dict[str, Dict[str, Any]] = {}

        if sp_config:
            prices = sp_config.get("prices") or {}
            original_price = _to_float((prices.get("oldPrice") or {}).get("amount"))
            current_price = _to_float((prices.get("finalPrice") or {}).get("amount"))
            if current_price is not None and original_price is None:
                original_price = current_price

            attributes = sp_config.get("attributes") or {}
            for attr in attributes.values():
                for opt in attr.get("options") or []:
                    label = (opt.get("label") or "").strip()
                    if not label:
                        continue
                    in_stock = bool(opt.get("products"))
                    size_detail[label] = {
                        "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
                        "ean": "0000000000000",
                    }

        if not size_detail:
            # 非配置型商品(单尺码)兜底: 只要页面标记可售就算有货
            in_stock = bool(data.get("offers"))
            size_detail["One Size"] = {
                "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
                "ean": "0000000000000",
            }

        if current_price is None:
            offers = data.get("offers") or []
            offers = offers if isinstance(offers, list) else [offers]
            if offers:
                current_price = _to_float(offers[0].get("price"))
                original_price = original_price if original_price is not None else current_price

        # 5. 尺码行
        product_size, product_size_detail = self.build_size_lines(size_detail, gender)

        return {
            "Product Code": product_code,
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
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


def magrigg_fetch_info(max_workers: int = 4):
    """主函数"""
    setup_logging()

    fetcher = MagriggFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=0,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Magrigg 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    magrigg_fetch_info(max_workers=4)
