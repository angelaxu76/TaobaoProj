# -*- coding: utf-8 -*-
"""
文本处理工具
统一处理所有采集脚本的文本清洗逻辑，消除重复代码

重复率: 在 8+ 个采集脚本中重复出现
"""

from __future__ import annotations

import re
import html
import unicodedata
from typing import Optional

# ================== 文本清洗 ==================

def clean_text(
    text: str,
    maxlen: int = 500,
    remove_html: bool = True,
    normalize_whitespace: bool = True,
    decode_entities: bool = True,
) -> str:
    """
    清理文本 - 去除HTML标签、实体、多余空白

    Args:
        text: 原始文本
        maxlen: 最大长度 (超出截断)
        remove_html: 是否移除HTML标签
        normalize_whitespace: 是否标准化空白字符
        decode_entities: 是否解码HTML实体

    Returns:
        清理后的文本

    Examples:
        >>> clean_text("<p>Hello &nbsp; World</p>")
        "Hello World"

        >>> clean_text("Very long text...", maxlen=10)
        "Very long ..."
    """
    if not text:
        return "No Data"

    t = text

    # 1. 解码 HTML 实体
    if decode_entities:
        t = html.unescape(t)

    # 2. 移除 HTML 标签
    if remove_html:
        t = re.sub(r"<[^>]+>", " ", t)

    # 3. 标准化空白
    if normalize_whitespace:
        t = re.sub(r"\s+", " ", t).strip()

    # 4. 截断
    if maxlen and len(t) > maxlen:
        t = t[:maxlen].rstrip() + "..."

    return t if t else "No Data"


def clean_description(desc: str, maxlen: int = 500) -> str:
    """
    清理商品描述 (应用所有清洗规则)

    Args:
        desc: 原始描述

    Returns:
        清理后的描述

    Examples:
        >>> clean_description("<div>Product description</div>")
        "Product description"
    """
    return clean_text(desc, maxlen=maxlen, remove_html=True)


def clean_title(title: str, maxlen: int = 200) -> str:
    """
    清理商品标题

    Args:
        title: 原始标题

    Returns:
        清理后的标题
    """
    return clean_text(title, maxlen=maxlen, remove_html=True)


def strip_product_code_from_text(text: str, product_code: str) -> str:
    """
    从文本中移除 Product Code (避免重复显示)

    Args:
        text: 原始文本 (描述、标题等)
        product_code: Barbour Product Code

    Returns:
        移除编码后的文本

    Examples:
        >>> strip_product_code_from_text("Ashby Jacket MWX0339NY91", "MWX0339NY91")
        "Ashby Jacket"
    """
    if not text or not product_code or product_code == "No Data":
        return clean_text(text)

    # 移除编码
    cleaned = re.sub(rf"\b{re.escape(product_code)}\b", "", text)

    return clean_text(cleaned)


# ================== 颜色文本处理 ==================

def normalize_color_name(color: str) -> str:
    """
    标准化颜色名称

    处理逻辑:
    1. 去除颜色编码后缀 (如 "Olive OL71" → "Olive")
    2. 取第一个词 (如 "Navy Blue" → "Navy")
    3. 小写化

    Args:
        color: 原始颜色字符串

    Returns:
        标准化的颜色名

    Examples:
        >>> normalize_color_name("Olive OL71")
        "olive"

        >>> normalize_color_name("Navy NY91")
        "navy"

        >>> normalize_color_name("Black/White")
        "black"
    """
    if not color or color == "No Data":
        return ""

    c = color.strip()

    # 去除颜色编码 (如 OL71, NY91, BK11)
    c = re.sub(r"\s+[A-Z]{1,3}\d{2,3}\b", "", c).strip()

    # 取斜杠前的第一部分
    c = c.split("/")[0].strip()

    # 取减号前的第一部分
    c = c.split("-")[0].strip()

    # 取双空格前的第一部分
    c = c.split("  ")[0].strip()

    # 只保留字母和空格
    c = re.sub(r"[^A-Za-z\s]", " ", c).strip()

    # 标准化空白
    c = re.sub(r"\s+", " ", c)

    return c.lower()


def extract_color_code_suffix(color: str) -> Optional[str]:
    """
    提取颜色编码后缀

    Args:
        color: 颜色字符串 (如 "Olive OL71")

    Returns:
        颜色编码 (如 "OL71")，或 None

    Examples:
        >>> extract_color_code_suffix("Olive OL71")
        "OL71"

        >>> extract_color_code_suffix("Navy NY91")
        "NY91"
    """
    if not color:
        return None

    # 匹配 2-3 字母 + 2-3 数字
    m = re.search(r"\b([A-Z]{2,3}\d{2,3})\b", color)
    if m:
        return m.group(1)

    return None


# ================== URL 处理 ==================

def normalize_url(url: str) -> str:
    """
    标准化 URL (去除锚点、查询参数)

    Args:
        url: 原始URL

    Returns:
        标准化的URL

    Examples:
        >>> normalize_url("https://example.com/product#reviews")
        "https://example.com/product"

        >>> normalize_url("https://example.com/product?ref=123")
        "https://example.com/product"
    """
    if not url:
        return ""

    u = url.strip()

    # 去除锚点
    u = re.sub(r"#.*$", "", u)

    # 可选: 去除查询参数 (根据需要启用)
    # u = re.sub(r"\?.*$", "", u)

    return u


def safe_filename(name: str, maxlen: int = 120) -> str:
    """
    生成安全的文件名 (移除特殊字符)

    Args:
        name: 原始文件名
        maxlen: 最大长度

    Returns:
        安全的文件名

    Examples:
        >>> safe_filename("Barbour Ashby Jacket (Navy)")
        "Barbour_Ashby_Jacket_Navy"

        >>> safe_filename("MWX0339NY91")
        "MWX0339NY91"
    """
    if not name:
        return "NoData"

    # 替换非字母数字字符为下划线
    s = re.sub(r"[^\w\-]+", "_", name.strip())

    # 合并多个下划线
    s = re.sub(r"_+", "_", s)

    # 截断
    s = s[:maxlen].strip("_")

    return s if s else "NoData"


# ================== 文本分割 ==================

def split_name_and_color(text: str, separator: str = "|") -> tuple[str, str]:
    """
    从标题中分割名称和颜色

    常见格式:
    - "Barbour Ashby Jacket | Olive"
    - "Barbour Ashby Jacket - Olive"

    Args:
        text: 原始标题
        separator: 分隔符 (默认 "|")

    Returns:
        (name, color)

    Examples:
        >>> split_name_and_color("Barbour Ashby | Olive")
        ("Barbour Ashby", "Olive")

        >>> split_name_and_color("Barbour Ashby - Olive", separator="-")
        ("Barbour Ashby", "Olive")
    """
    if not text:
        return "No Data", "No Data"

    if separator in text:
        parts = text.split(separator, 1)
        name = clean_text(parts[0], maxlen=200)
        color = clean_text(parts[1], maxlen=100)
        return name, color

    # 没有分隔符，全部作为名称
    return clean_text(text, maxlen=200), "No Data"


# ================== ASCII 标准化 ==================

def normalize_ascii(text: str) -> str:
    """
    将文本标准化为 ASCII (去除重音符号等)

    Args:
        text: 原始文本

    Returns:
        ASCII化的文本

    Examples:
        >>> normalize_ascii("Café")
        "Cafe"

        >>> normalize_ascii("Naïve")
        "Naive"
    """
    if not text:
        return ""

    # NFKD 分解 + ASCII编码
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    return ascii_text


def tokenize(text: str, min_length: int = 3) -> list[str]:
    """
    将文本分词 (用于匹配)

    处理逻辑:
    1. ASCII标准化
    2. 小写化
    3. 只保留字母数字
    4. 过滤短词

    Args:
        text: 原始文本
        min_length: 最小词长

    Returns:
        词列表

    Examples:
        >>> tokenize("Barbour Ashby Wax Jacket")
        ["barbour", "ashby", "wax", "jacket"]
    """
    if not text:
        return []

    # ASCII化 + 小写
    t = normalize_ascii(text).lower()

    # 只保留字母数字和空格
    t = re.sub(r"[^a-z0-9\s]", " ", t)

    # 分词并过滤短词
    words = [w for w in t.split() if len(w) >= min_length]

    return words


def dedupe_keep_order(words: list[str]) -> list[str]:
    """
    去重并保持顺序

    Args:
        words: 词列表

    Returns:
        去重后的词列表

    Examples:
        >>> dedupe_keep_order(["a", "b", "a", "c"])
        ["a", "b", "c"]
    """
    seen = set()
    result = []

    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)

    return result


# ================== 数字提取 ==================

def extract_number(text: str) -> Optional[float]:
    """
    从文本中提取数字

    Args:
        text: 包含数字的文本

    Returns:
        数字 (float)，或 None

    Examples:
        >>> extract_number("Size: 10")
        10.0

        >>> extract_number("Price: £179.99")
        179.99
    """
    if not text:
        return None

    # 匹配整数或小数
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        return float(m.group(1))

    return None


# ================== 布尔值判断 ==================

def is_truthy(value: any) -> bool:
    """
    判断值是否为真 (兼容多种类型)

    Args:
        value: 任意值

    Returns:
        True/False

    Examples:
        >>> is_truthy("yes")
        True

        >>> is_truthy("false")
        False

        >>> is_truthy(1)
        True
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value > 0

    if isinstance(value, str):
        value_lower = value.lower().strip()
        return value_lower in ["true", "yes", "1", "y", "on", "有货"]

    return bool(value)
