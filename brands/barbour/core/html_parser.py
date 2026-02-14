# -*- coding: utf-8 -*-
"""
HTML/JSON-LD 解析工具
统一处理所有采集脚本的HTML解析逻辑，消除重复代码

重复率: 在 8+ 个采集脚本中重复出现
"""

from __future__ import annotations

import json
import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup

# ================== JSON-LD 解析 ==================

def extract_jsonld(
    soup: BeautifulSoup,
    target_type: str | List[str] = "Product",
) -> Optional[Dict[str, Any]]:
    """
    从 HTML 中提取 JSON-LD 结构化数据

    Args:
        soup: BeautifulSoup对象
        target_type: 目标类型 ("Product", "ProductGroup", ["Product", "Offer"])

    Returns:
        JSON-LD字典，或 None (未找到)

    Examples:
        >>> soup = BeautifulSoup(html, "html.parser")
        >>> jsonld = extract_jsonld(soup, "Product")
        >>> print(jsonld.get("name"))
    """
    if isinstance(target_type, str):
        target_types = [target_type]
    else:
        target_types = target_type

    # 查找所有 JSON-LD script 标签
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw_text = script.get_text(strip=True)
            if not raw_text:
                continue

            # 解析 JSON
            data = json.loads(raw_text)

            # 处理数组形式
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and _is_target_type(item, target_types):
                        return item

            # 处理单个对象
            if isinstance(data, dict) and _is_target_type(data, target_types):
                return data

        except (json.JSONDecodeError, Exception):
            continue

    return None


def _is_target_type(data: Dict, target_types: List[str]) -> bool:
    """检查JSON-LD对象是否匹配目标类型"""
    obj_type = data.get("@type", "")

    if isinstance(obj_type, str):
        return obj_type.lower() in [t.lower() for t in target_types]

    if isinstance(obj_type, list):
        return any(t.lower() in [tt.lower() for tt in target_types] for t in obj_type)

    return False


def extract_jsonld_field(
    soup: BeautifulSoup,
    field: str,
    target_type: str = "Product",
    default: Any = None,
) -> Any:
    """
    从 JSON-LD 中提取单个字段

    Args:
        soup: BeautifulSoup对象
        field: 字段名 (如 "name", "description", "sku")
        target_type: JSON-LD类型
        default: 默认值

    Returns:
        字段值，或默认值

    Examples:
        >>> name = extract_jsonld_field(soup, "name")
        >>> sku = extract_jsonld_field(soup, "sku", default="N/A")
    """
    jsonld = extract_jsonld(soup, target_type)
    if jsonld:
        return jsonld.get(field, default)
    return default


# ================== Meta 标签解析 ==================

def extract_meta_tag(
    soup: BeautifulSoup,
    name: str,
    attr: str = "content",
    name_attr: str = "name",
) -> Optional[str]:
    """
    提取 meta 标签的内容

    Args:
        soup: BeautifulSoup对象
        name: meta 标签的 name 或 property 属性值
        attr: 要提取的属性 (默认 "content")
        name_attr: 名称属性 (默认 "name", 也可以是 "property")

    Returns:
        meta 标签的内容，或 None

    Examples:
        >>> # <meta name="description" content="Product description">
        >>> desc = extract_meta_tag(soup, "description")

        >>> # <meta property="og:title" content="Product Title">
        >>> title = extract_meta_tag(soup, "og:title", name_attr="property")
    """
    # 尝试 name 属性
    tag = soup.find("meta", attrs={name_attr: name})
    if tag and tag.get(attr):
        return tag[attr]

    # 如果 name_attr 是 "name", 再尝试 "property"
    if name_attr == "name":
        tag = soup.find("meta", attrs={"property": name})
        if tag and tag.get(attr):
            return tag[attr]

    # 如果 name_attr 是 "property", 再尝试 "name"
    if name_attr == "property":
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get(attr):
            return tag[attr]

    return None


def extract_og_tag(soup: BeautifulSoup, og_type: str) -> Optional[str]:
    """
    提取 Open Graph (og:*) 标签内容

    Args:
        soup: BeautifulSoup对象
        og_type: OG类型 (如 "title", "description", "image")

    Returns:
        OG标签的内容，或 None

    Examples:
        >>> title = extract_og_tag(soup, "title")
        >>> image = extract_og_tag(soup, "image")
    """
    full_name = f"og:{og_type}" if not og_type.startswith("og:") else og_type
    return extract_meta_tag(soup, full_name, name_attr="property")


def extract_twitter_tag(soup: BeautifulSoup, twitter_type: str) -> Optional[str]:
    """
    提取 Twitter Card 标签内容

    Args:
        soup: BeautifulSoup对象
        twitter_type: Twitter类型 (如 "title", "description", "image")

    Returns:
        Twitter标签的内容，或 None

    Examples:
        >>> title = extract_twitter_tag(soup, "title")
    """
    full_name = f"twitter:{twitter_type}" if not twitter_type.startswith("twitter:") else twitter_type
    return extract_meta_tag(soup, full_name)


# ================== 价格解析 ==================

def extract_price_from_text(text: str) -> Optional[float]:
    """
    从文本中提取价格 (支持多种格式)

    支持格式:
    - £179.99
    - $179.99
    - 179.99
    - 17999 (便士，自动转为英镑)

    Args:
        text: 包含价格的文本

    Returns:
        价格 (float)，或 None

    Examples:
        >>> extract_price_from_text("£179.99")
        179.99

        >>> extract_price_from_text("17999")
        179.99

        >>> extract_price_from_text("$179.99")
        179.99
    """
    if not text:
        return None

    cleaned = text.strip()

    # 1. 带货币符号: £179.99 或 $179.99
    m_symbol = re.search(r"[£$€]\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_symbol:
        return float(m_symbol.group(1))

    # 2. 便士格式: 17999 (3-5位纯数字)
    m_pence = re.search(r"^([0-9]{3,5})$", cleaned)
    if m_pence:
        try:
            pence_val = int(m_pence.group(1))
            return round(pence_val / 100.0, 2)
        except Exception:
            pass

    # 3. 纯数字: 179.99 或 179
    m_plain = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if m_plain:
        return float(m_plain.group(1))

    return None


def extract_prices_from_element(
    price_element: Any,
    original_selector: str = 'span[data-testid="ticket-price"]',
    discount_selector: str = 'span[class*="isDiscounted"]',
) -> tuple[Optional[float], Optional[float]]:
    """
    从价格容器元素中提取原价和折扣价

    Args:
        price_element: 价格容器元素 (BeautifulSoup Tag)
        original_selector: 原价选择器
        discount_selector: 折扣价选择器

    Returns:
        (original_price, discount_price) 或 (price, None)

    Examples:
        >>> price_block = soup.select_one('div.price')
        >>> original, discount = extract_prices_from_element(price_block)
    """
    if not price_element:
        return None, None

    original_price = None
    discount_price = None

    # 提取折扣价
    discount_tag = price_element.select_one(discount_selector)
    if discount_tag:
        discount_price = extract_price_from_text(discount_tag.get_text(strip=True))

    # 提取原价
    original_tag = price_element.select_one(original_selector)
    if original_tag:
        original_price = extract_price_from_text(original_tag.get_text(strip=True))

    # 兜底: 从 data-testvalue 属性读取
    if original_price is None:
        testvalue = price_element.get("data-testvalue")
        if testvalue:
            original_price = extract_price_from_text(testvalue)

    # 兜底: 从第一个 span 读取
    if original_price is None:
        first_span = price_element.find("span")
        if first_span:
            original_price = extract_price_from_text(first_span.get_text(strip=True))

    return original_price, discount_price


# ================== 图片提取 ==================

def extract_image_urls(
    soup: BeautifulSoup,
    selectors: List[str] = None,
    limit: int = 10,
) -> List[str]:
    """
    从 HTML 中提取商品图片URL

    Args:
        soup: BeautifulSoup对象
        selectors: CSS选择器列表 (默认常见模式)
        limit: 最大图片数量

    Returns:
        图片URL列表

    Examples:
        >>> images = extract_image_urls(soup)
        >>> main_image = images[0] if images else None
    """
    if selectors is None:
        selectors = [
            'img[data-testid*="product-image"]',
            'img.product-image',
            'img[itemprop="image"]',
            'meta[property="og:image"]',
            'img[alt*="product"]',
        ]

    urls = []
    seen = set()

    for selector in selectors:
        # img 标签
        if selector.startswith("img"):
            for img in soup.select(selector):
                url = img.get("src") or img.get("data-src") or img.get("data-lazy")
                if url and url not in seen:
                    urls.append(url)
                    seen.add(url)
                    if len(urls) >= limit:
                        return urls

        # meta 标签
        elif selector.startswith("meta"):
            tag = soup.select_one(selector)
            if tag:
                url = tag.get("content")
                if url and url not in seen:
                    urls.append(url)
                    seen.add(url)

    return urls[:limit]


# ================== 尺码提取 ==================

def extract_sizes_from_select(soup: BeautifulSoup) -> List[str]:
    """
    从 select 下拉框中提取尺码选项

    Args:
        soup: BeautifulSoup对象

    Returns:
        尺码列表

    Examples:
        >>> sizes = extract_sizes_from_select(soup)
        >>> # ["S", "M", "L", "XL"]
    """
    sizes = []
    seen = set()

    # 查找尺码相关的 select 标签
    selectors = [
        'select[name*="size"]',
        'select[id*="size"]',
        'select[data-testid*="size"]',
        'select option',  # 兜底
    ]

    for selector in selectors:
        for option in soup.select(selector):
            text = option.get_text(strip=True)

            # 过滤空值和提示文本
            if not text or text.lower() in ["select size", "choose size", "size", "--"]:
                continue

            if text not in seen:
                sizes.append(text)
                seen.add(text)

    return sizes


# ================== Barbour Product Code 提取 ==================

def extract_barbour_code_from_text(text: str) -> Optional[str]:
    """
    从文本中提取 Barbour Product Code

    格式: MWX0339NY91 (3字母 + 4数字 + 2字母 + 2数字)

    Args:
        text: 包含Product Code的文本 (描述、标题等)

    Returns:
        Product Code，或 None

    Examples:
        >>> extract_barbour_code_from_text("Product: MWX0339NY91")
        "MWX0339NY91"

        >>> extract_barbour_code_from_text("Barbour Ashby Jacket")
        None
    """
    if not text:
        return None

    # Barbour编码格式: MWX0339NY91
    pattern = r"\b[A-Z]{2,3}\d{4}[A-Z]{2}\d{2}\b"

    # 优先取最后一个匹配 (通常在描述末尾)
    matches = list(re.finditer(pattern, text))
    if matches:
        return matches[-1].group(0)

    return None


def extract_barbour_code_from_description(soup: BeautifulSoup) -> Optional[str]:
    """
    从商品描述中提取 Barbour Product Code

    Args:
        soup: BeautifulSoup对象

    Returns:
        Product Code，或 None
    """
    # 尝试从 meta 描述
    desc = extract_meta_tag(soup, "description")
    if desc:
        code = extract_barbour_code_from_text(desc)
        if code:
            return code

    # 尝试从 JSON-LD 描述
    jsonld_desc = extract_jsonld_field(soup, "description")
    if jsonld_desc:
        code = extract_barbour_code_from_text(jsonld_desc)
        if code:
            return code

    # 尝试从页面文本
    for tag in soup.find_all(["p", "div", "span"]):
        text = tag.get_text(strip=True)
        code = extract_barbour_code_from_text(text)
        if code:
            return code

    return None
