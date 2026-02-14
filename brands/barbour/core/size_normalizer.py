# -*- coding: utf-8 -*-
"""
Barbour 尺码标准化工具
统一处理所有采集脚本的尺码标准化逻辑，消除重复代码

重复率: 在 8 个采集脚本中重复出现 (70%+ 重复)
"""

from __future__ import annotations

import re
from typing import Optional, List, Dict, Tuple, Set
from config import SETTINGS

# ================== 配置常量 ==================

DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# 尺码顺序配置
WOMEN_ORDER = ["4", "6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA_ORDER = ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30, 32, 34, ..., 50 (不含52)

# 字母尺码映射（标准化）
ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}


# ================== 核心函数 ==================

def normalize_size(token: str, gender: str) -> Optional[str]:
    """
    将原始尺码标准化为统一格式

    处理逻辑:
    1. 去除前缀 (UK, EU, US)
    2. 数字尺码: 女款 4-20, 男款 30-50 (偶数)
    3. 字母尺码: 通过 ALPHA_MAP 标准化

    Args:
        token: 原始尺码字符串 (如 "UK 10", "S", "XL", "36")
        gender: 性别 ("男款" / "女款" / "Men" / "Women")

    Returns:
        标准化后的尺码，或 None (无效尺码)

    Examples:
        >>> normalize_size("UK 10", "女款")
        "10"
        >>> normalize_size("S", "男款")
        "S"
        >>> normalize_size("52", "男款")
        None  # 男款数字尺码不包含52
    """
    if not token:
        return None

    # 标准化输入
    s = token.strip().upper()

    # 去除前缀和括号
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "").replace("SIZE ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)  # 去除括号
    s = re.sub(r"\s+", " ", s).strip()

    # 统一性别格式
    gender_lower = (gender or "").lower()
    is_women = "女" in gender_lower or "women" in gender_lower or "lady" in gender_lower or "ladies" in gender_lower
    is_men = "男" in gender_lower or "men" in gender_lower or "man" in gender_lower

    # 尝试数字尺码
    m = re.findall(r"\d{1,3}", s)
    if m:
        n = int(m[0])

        # 女款数字尺码: 4, 6, 8, 10, 12, 14, 16, 18, 20
        if is_women and n in {4, 6, 8, 10, 12, 14, 16, 18, 20}:
            return str(n)

        # 男款数字尺码: 30-50 (偶数, 排除52)
        if is_men:
            # 严格匹配
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)

            # 容错: 28-54 映射到最近的有效值
            if 28 <= n <= 54:
                candidate = n if n % 2 == 0 else n - 1
                candidate = max(30, min(50, candidate))
                return str(candidate)

        # 其他情况不返回
        return None

    # 尝试字母尺码
    key = s.replace("-", "").replace(" ", "")
    return ALPHA_MAP.get(key)


def choose_size_order_for_gender(gender: str, present_sizes: Set[str]) -> List[str]:
    """
    根据性别和已存在的尺码，选择完整的尺码顺序表

    逻辑:
    - 女款: 固定返回 4-20
    - 男款: 根据实际尺码选择字母系或数字系

    Args:
        gender: 性别 ("男款" / "女款")
        present_sizes: 已存在的尺码集合

    Returns:
        完整的尺码顺序列表

    Examples:
        >>> choose_size_order_for_gender("女款", {"4", "6", "8"})
        ["4", "6", "8", "10", "12", "14", "16", "18", "20"]

        >>> choose_size_order_for_gender("男款", {"S", "M", "L"})
        ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]

        >>> choose_size_order_for_gender("男款", {"30", "32", "34"})
        ["30", "32", "34", ..., "50"]
    """
    gender_lower = (gender or "").lower()

    # 女款固定
    if "女" in gender_lower or "women" in gender_lower:
        return WOMEN_ORDER[:]

    # 男款: 判断是字母系还是数字系
    has_num = any(k in MEN_NUM_ORDER for k in present_sizes)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in present_sizes)

    # 只有数字系
    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]

    # 只有字母系
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]

    # 混合情况: 取数量多的
    if has_num or has_alpha:
        num_count = sum(1 for k in present_sizes if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in present_sizes if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]

    # 默认字母系
    return MEN_ALPHA_ORDER[:]


def sort_sizes(sizes: List[str], gender: str) -> List[str]:
    """
    按照标准顺序排序尺码

    Args:
        sizes: 尺码列表
        gender: 性别

    Returns:
        排序后的尺码列表

    Examples:
        >>> sort_sizes(["L", "S", "M"], "男款")
        ["S", "M", "L"]

        >>> sort_sizes(["10", "6", "8"], "女款")
        ["6", "8", "10"]
    """
    if not sizes:
        return []

    gender_lower = (gender or "").lower()

    # 女款排序
    if "女" in gender_lower or "women" in gender_lower:
        return [s for s in WOMEN_ORDER if s in sizes]

    # 男款排序: 字母优先，然后数字
    alpha_sizes = [s for s in MEN_ALPHA_ORDER if s in sizes]
    num_sizes = [s for s in MEN_NUM_ORDER if s in sizes]

    return alpha_sizes + num_sizes


def parse_size_detail(size_detail_str: str) -> Dict[str, Dict]:
    """
    解析 Size Detail 字符串

    Args:
        size_detail_str: "S:3:EAN001;M:0:EAN002;L:5:EAN003"

    Returns:
        {
            "S": {"stock_count": 3, "ean": "EAN001"},
            "M": {"stock_count": 0, "ean": "EAN002"},
            "L": {"stock_count": 5, "ean": "EAN003"},
        }

    Examples:
        >>> parse_size_detail("S:3:EAN001;M:0:EAN002")
        {"S": {"stock_count": 3, "ean": "EAN001"}, "M": {"stock_count": 0, "ean": "EAN002"}}
    """
    if not size_detail_str or size_detail_str == "No Data":
        return {}

    result = {}

    for item in size_detail_str.split(";"):
        parts = item.split(":")
        if len(parts) < 2:
            continue

        size = parts[0].strip()
        stock_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        ean = parts[2].strip() if len(parts) > 2 else ""

        result[size] = {
            "stock_count": stock_count,
            "ean": ean,
        }

    return result


def build_size_lines_from_detail(
    size_detail: Dict[str, Dict],
    gender: str,
    default_stock: int = DEFAULT_STOCK_COUNT,
) -> Tuple[str, str]:
    """
    从 size_detail 字典生成 Product Size 和 Product Size Detail 字符串

    核心逻辑:
    1. 标准化所有尺码
    2. 汇总库存状态 (有货优先)
    3. 选择单一尺码系 (男款字母系或数字系二选一)
    4. 填充缺失尺码 (无货)
    5. 生成输出字符串

    Args:
        size_detail:
            {
                "UK 10": {"stock_count": 3, "ean": "EAN001"},
                "S": {"stock_count": 0, "ean": "EAN002"},
            }
        gender: 性别 ("男款" / "女款")
        default_stock: 默认库存数 (当有货时)

    Returns:
        (
            "S:有货;M:无货;L:有货",           # Product Size
            "S:3:EAN001;M:0:;L:3:EAN003"     # Product Size Detail
        )
    """
    if not size_detail:
        return ("No Data", "No Data")

    # 1) 汇总标准化后的尺码 (有货优先)
    bucket_status: Dict[str, str] = {}
    bucket_stock: Dict[str, int] = {}
    bucket_ean: Dict[str, str] = {}

    for raw_size, meta in size_detail.items():
        norm_size = normalize_size(raw_size, gender or "男款")
        if not norm_size:
            continue

        stock = int(meta.get("stock_count", 0) or 0)
        ean = meta.get("ean", "")
        status = "有货" if stock > 0 else "无货"

        # 如果已存在，优先保留"有货"状态
        prev_status = bucket_status.get(norm_size)
        if prev_status is None or (prev_status == "无货" and status == "有货"):
            bucket_status[norm_size] = status
            bucket_stock[norm_size] = default_stock if stock > 0 else 0
            bucket_ean[norm_size] = ean

    if not bucket_status:
        return ("No Data", "No Data")

    # 2) 选择完整尺码顺序表
    present_sizes = set(bucket_status.keys())
    full_order = choose_size_order_for_gender(gender or "男款", present_sizes)

    # 2.5) 清理不属于所选尺码系的键 (防止混合)
    valid_keys = set(full_order)
    for size in list(bucket_status.keys()):
        if size not in valid_keys:
            del bucket_status[size]
            del bucket_stock[size]
            if size in bucket_ean:
                del bucket_ean[size]

    # 3) 填充缺失尺码 (无货)
    for size in full_order:
        if size not in bucket_status:
            bucket_status[size] = "无货"
            bucket_stock[size] = 0
            bucket_ean[size] = ""

    # 4) 按顺序生成输出
    sorted_sizes = [s for s in full_order if s in bucket_status]

    # Product Size: "S:有货;M:无货;L:有货"
    product_size = ";".join([f"{s}:{bucket_status[s]}" for s in sorted_sizes])

    # Product Size Detail: "S:3:EAN001;M:0:;L:3:EAN003"
    product_size_detail = ";".join([
        f"{s}:{bucket_stock[s]}:{bucket_ean.get(s, '')}"
        for s in sorted_sizes
    ])

    return (product_size, product_size_detail)


def format_size_str_simple(sizes: List[str], gender: str) -> str:
    """
    简单格式化尺码为 "S:有货;M:有货;L:无货"

    用于没有详细库存信息的场景 (全部标记为有货)

    Args:
        sizes: 尺码列表 (如 ["S", "M", "L"])
        gender: 性别

    Returns:
        "S:有货;M:有货;L:有货"
    """
    if not sizes:
        return "No Data"

    sorted_sizes = sort_sizes(sizes, gender)
    return ";".join([f"{s}:有货" for s in sorted_sizes])


def format_size_detail_simple(
    sizes: List[str],
    gender: str,
    default_stock: int = DEFAULT_STOCK_COUNT,
) -> str:
    """
    简单格式化尺码详情为 "S:3:;M:3:;L:3:"

    用于没有EAN信息的场景

    Args:
        sizes: 尺码列表
        gender: 性别
        default_stock: 默认库存数

    Returns:
        "S:3:;M:3:;L:3:"
    """
    if not sizes:
        return "No Data"

    sorted_sizes = sort_sizes(sizes, gender)
    return ";".join([f"{s}:{default_stock}:" for s in sorted_sizes])


# ================== 工具函数 ==================

def clean_size_token(token: str) -> str:
    """
    清理尺码字符串 (去除多余字符)

    Args:
        token: 原始尺码

    Returns:
        清理后的尺码
    """
    if not token:
        return ""

    s = token.strip().upper()
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)
    s = re.sub(r"\s+", " ", s)

    return s.strip()


def is_valid_size(size: str, gender: str) -> bool:
    """
    检查尺码是否有效

    Args:
        size: 尺码字符串
        gender: 性别

    Returns:
        True/False
    """
    normalized = normalize_size(size, gender)
    return normalized is not None
