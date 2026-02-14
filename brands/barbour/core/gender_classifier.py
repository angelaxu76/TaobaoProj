# -*- coding: utf-8 -*-
"""
Barbour 性别分类器
统一处理所有采集脚本的性别推断逻辑，消除重复代码

重复率: 在 8+ 个采集脚本中重复出现
"""

from __future__ import annotations

import re
from typing import Optional, Literal

# ================== 类型定义 ==================

GenderType = Literal["Men", "Women", "Kids", "Unisex", "No Data"]
GenderTypeCN = Literal["男款", "女款", "童款", "中性", "未知"]

# ================== 性别匹配模式 ==================

GENDER_PATTERNS = {
    "Women": [
        r"\b(women|woman|women's|womens|ladies|lady|female|她)\b",
        r"/womens?/",
        r"[-_]w[-_]",
        r"女",
    ],
    "Men": [
        r"\b(men|men's|mens|man|male|他)\b",
        r"/mens?/",
        r"[-_]m[-_]",
        r"男",
    ],
    "Kids": [
        r"\b(kids?|kid's|boy|boys|girl|girls|children|junior|youth)\b",
        r"/kids?/",
        r"童",
    ],
}

# Barbour Product Code 前缀规则
# M 开头 = Men (如 MWX0339NY91)
# L 开头 = Women (如 LWX1234BK11)
CODE_PREFIX_RULES = {
    "M": "Men",
    "L": "Women",
    "B": "Kids",    # Boy
    "G": "Kids",    # Girl
    "K": "Kids",    # Kids
}


# ================== 核心函数 ==================

def infer_gender(
    text: str = "",
    url: str = "",
    product_code: str = "",
    html: str = "",
    output_format: Literal["en", "cn"] = "en",
) -> str:
    """
    多维度性别推断 - 统一接口

    优先级:
    1. Product Code 前缀 (最可靠: M=Men, L=Women)
    2. URL 路径 (/mens/, /womens/)
    3. 文本内容 (标题、描述)
    4. 兜底: Unisex / 未知

    Args:
        text: 商品标题、描述等文本
        url: 商品URL
        product_code: Barbour商品编码 (如 MWX0339NY91)
        html: 完整HTML (可选)
        output_format: 输出格式 ("en" = Men/Women, "cn" = 男款/女款)

    Returns:
        性别标识 (英文或中文)

    Examples:
        >>> infer_gender(product_code="MWX0339NY91")
        "Men"

        >>> infer_gender(url="https://example.com/mens/jackets")
        "Men"

        >>> infer_gender(text="Barbour Women's Classic Jacket")
        "Women"

        >>> infer_gender(text="童装夹克", output_format="cn")
        "童款"
    """
    # 1. 从 Product Code 推断 (最可靠)
    if product_code:
        gender_from_code = infer_from_code(product_code)
        if gender_from_code != "No Data":
            return _format_output(gender_from_code, output_format)

    # 2. 从 URL 推断
    if url:
        gender_from_url = infer_from_url(url)
        if gender_from_url != "No Data":
            return _format_output(gender_from_url, output_format)

    # 3. 从文本推断 (标题、描述)
    if text:
        gender_from_text = infer_from_text(text)
        if gender_from_text != "No Data":
            return _format_output(gender_from_text, output_format)

    # 4. 从 HTML 全文推断 (兜底)
    if html:
        gender_from_html = infer_from_text(html)
        if gender_from_html != "No Data":
            return _format_output(gender_from_html, output_format)

    # 5. 兜底
    return "未知" if output_format == "cn" else "No Data"


def infer_from_code(product_code: str) -> GenderType:
    """
    从 Barbour Product Code 推断性别

    规则:
    - M开头 = Men (如 MWX0339NY91)
    - L开头 = Women (如 LWX1234BK11)
    - B/G/K开头 = Kids

    Args:
        product_code: Barbour商品编码

    Returns:
        "Men" / "Women" / "Kids" / "No Data"

    Examples:
        >>> infer_from_code("MWX0339NY91")
        "Men"

        >>> infer_from_code("LWX1234BK11")
        "Women"

        >>> infer_from_code("UNKNOWN")
        "No Data"
    """
    if not product_code:
        return "No Data"

    code_upper = product_code.strip().upper()

    # 检查前缀
    for prefix, gender in CODE_PREFIX_RULES.items():
        if code_upper.startswith(prefix):
            return gender  # type: ignore

    return "No Data"


def infer_from_url(url: str) -> GenderType:
    """
    从 URL 路径推断性别

    匹配规则:
    - /mens/ 或 /men/ → Men
    - /womens/ 或 /women/ → Women
    - /kids/ → Kids

    Args:
        url: 商品URL

    Returns:
        "Men" / "Women" / "Kids" / "No Data"

    Examples:
        >>> infer_from_url("https://example.com/mens/jackets")
        "Men"

        >>> infer_from_url("https://example.com/products/womens-coats")
        "Women"
    """
    if not url:
        return "No Data"

    url_lower = url.lower()

    # 按优先级匹配
    for gender, patterns in GENDER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower, re.IGNORECASE):
                return gender  # type: ignore

    return "No Data"


def infer_from_text(text: str) -> GenderType:
    """
    从文本内容推断性别

    匹配规则:
    - 关键词: women/women's/ladies → Women
    - 关键词: men/men's → Men
    - 关键词: kids/boy/girl → Kids

    Args:
        text: 标题、描述或其他文本

    Returns:
        "Men" / "Women" / "Kids" / "No Data"

    Examples:
        >>> infer_from_text("Barbour Women's Classic Jacket")
        "Women"

        >>> infer_from_text("Men's Wax Jacket")
        "Men"

        >>> infer_from_text("Kids Quilted Coat")
        "Kids"
    """
    if not text:
        return "No Data"

    text_lower = text.lower()

    # 优先级: Women > Kids > Men (避免 "women" 被 "men" 误匹配)
    priority_order = ["Women", "Kids", "Men"]

    for gender in priority_order:
        patterns = GENDER_PATTERNS.get(gender, [])
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return gender  # type: ignore

    return "No Data"


def infer_from_html(html: str) -> GenderType:
    """
    从完整 HTML 推断性别 (兜底方法)

    Args:
        html: HTML源码

    Returns:
        "Men" / "Women" / "Kids" / "No Data"
    """
    return infer_from_text(html)


# ================== 格式化输出 ==================

def _format_output(gender: str, output_format: str) -> str:
    """
    格式化性别输出

    Args:
        gender: 英文性别 ("Men" / "Women" / "Kids")
        output_format: 输出格式 ("en" / "cn")

    Returns:
        格式化后的性别字符串
    """
    if output_format == "cn":
        mapping = {
            "Men": "男款",
            "Women": "女款",
            "Kids": "童款",
            "Unisex": "中性",
            "No Data": "未知",
        }
        return mapping.get(gender, "未知")

    # 英文格式
    return gender


def to_chinese(gender_en: str) -> GenderTypeCN:
    """
    英文性别转中文

    Args:
        gender_en: 英文性别

    Returns:
        中文性别

    Examples:
        >>> to_chinese("Men")
        "男款"

        >>> to_chinese("Women")
        "女款"
    """
    mapping = {
        "Men": "男款",
        "Women": "女款",
        "Kids": "童款",
        "Unisex": "中性",
        "No Data": "未知",
    }
    return mapping.get(gender_en, "未知")  # type: ignore


def to_english(gender_cn: str) -> GenderType:
    """
    中文性别转英文

    Args:
        gender_cn: 中文性别

    Returns:
        英文性别

    Examples:
        >>> to_english("男款")
        "Men"

        >>> to_english("女款")
        "Women"
    """
    mapping = {
        "男款": "Men",
        "女款": "Women",
        "童款": "Kids",
        "中性": "Unisex",
        "未知": "No Data",
    }
    return mapping.get(gender_cn, "No Data")  # type: ignore


# ================== 向后兼容函数 ==================

def infer_gender_from_title(title_or_name: str) -> str:
    """
    从标题推断性别 (向后兼容)

    Args:
        title_or_name: 标题或名称

    Returns:
        "女款" / "男款" / "童款" / "未知"
    """
    return infer_gender(text=title_or_name, output_format="cn")


def infer_gender_from_name(name: str) -> str:
    """
    从名称推断性别 (向后兼容)

    Args:
        name: 商品名称

    Returns:
        "女款" / "男款" / "童款" / "未知"
    """
    return infer_gender(text=name, output_format="cn")


def extract_gender(
    title: str = "",
    url: str = "",
    html: str = "",
    product_code: str = "",
) -> str:
    """
    综合提取性别 (向后兼容)

    Args:
        title: 标题
        url: URL
        html: HTML
        product_code: 商品编码

    Returns:
        英文性别 ("Men" / "Women" / "Kids" / "No Data")
    """
    return infer_gender(
        text=title,
        url=url,
        html=html,
        product_code=product_code,
        output_format="en",
    )


# ================== 验证函数 ==================

def is_valid_gender(gender: str) -> bool:
    """
    检查性别值是否有效

    Args:
        gender: 性别字符串

    Returns:
        True/False
    """
    valid_values = {
        "Men", "Women", "Kids", "Unisex",
        "男款", "女款", "童款", "中性",
    }
    return gender in valid_values


def normalize_gender(gender: str, output_format: Literal["en", "cn"] = "en") -> str:
    """
    标准化性别值

    Args:
        gender: 原始性别字符串 (可能是各种格式)
        output_format: 输出格式

    Returns:
        标准化后的性别

    Examples:
        >>> normalize_gender("WOMEN")
        "Women"

        >>> normalize_gender("male", "en")
        "Men"

        >>> normalize_gender("女", "cn")
        "女款"
    """
    gender_lower = (gender or "").lower()

    # 映射各种变体
    if any(k in gender_lower for k in ["women", "woman", "ladies", "lady", "female", "她", "女"]):
        return "女款" if output_format == "cn" else "Women"

    if any(k in gender_lower for k in ["men", "man", "male", "他", "男"]):
        return "男款" if output_format == "cn" else "Men"

    if any(k in gender_lower for k in ["kids", "kid", "boy", "girl", "children", "童"]):
        return "童款" if output_format == "cn" else "Kids"

    return "未知" if output_format == "cn" else "No Data"
