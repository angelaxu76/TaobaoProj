# -*- coding: utf-8 -*-
"""
clean_size_for_barbour: Barbour/服装优先的尺码清洗与归一化（保底不丢）
- 识别成功：返回统一规范值（如 2XL→XXL，UK 10→10）
- 识别失败：返回原始值（strip 后），并打印⚠️日志
"""

from __future__ import annotations
import re
from typing import Optional

# —— 常见别名与同义写法（完全/去空格/去连字符匹配）——
ALIASES = {
    # 大码等价
    "1XL": "XL",
    "2XL": "XXL",
    "3XL": "XXXL",
    "4XL": "XXXXL",
    "5XL": "XXXXXL",
    "6XL": "XXXXXXL",

    # 小码等价
    "XS": "XS",
    "2XS": "XXS",
    "XXS": "XXS",
    "3XS": "XXXS",
    "XXXS": "XXXS",

    # 英文描述别写
    "XSMALL": "XS",
    "X-SMALL": "XS",
    "X SMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "X-LARGE": "XL",
    "XLARGE": "XL",
    "X LARGE": "XL",

    # 均码
    "ONE SIZE": "ONESIZE",
    "ONE-SIZE": "ONESIZE",
    "ONESIZE": "ONESIZE",
    "O/S": "ONESIZE",
    "OS": "ONESIZE",
    "OSFM": "ONESIZE",       # One Size Fits Most
    "FREE SIZE": "ONESIZE",
    "FREESIZE": "ONESIZE",
    "F/S": "ONESIZE",
}

# —— 服装整码集合 ——（Barbour 以服装为主）
APPAREL_SIZES = {
    "XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL",
    "XXXXL", "XXXXXL", "XXXXXXL", "ONESIZE",
    *{str(s) for s in range(4, 24, 2)},    # 女装 UK 号 4–22
    *{str(s) for s in range(30, 56, 2)},   # 男装腰围 30–54
}

# —— 鞋类：EU 常见范围 ——（为兼容/容错，服装不受影响）
EU_SHOE_RANGE = {str(s) for s in range(35, 49)}  # 35–48

# 半码正则（2–15.5），支持 UK/EU/US 可选前缀与空格
RE_HALF = re.compile(r"^(?:UK|EU|US)?\s*([2-9](?:\.5)?|1[0-5](?:\.5)?)$",
                     flags=re.IGNORECASE)

def _norm(s: str) -> str:
    return (s or "").strip().upper()

def _squash(s: str) -> str:
    return _norm(s).replace(" ", "").replace("-", "")

def _clean_strict(raw_size: str) -> Optional[str]:
    """严格归一化；识别失败返回 None（由对外函数决定是否保留原样）"""
    if not raw_size:
        return None

    raw = _norm(raw_size)
    raw_ns = _squash(raw_size)

    # 1) 别名优先（完全 / 去空格连字符）
    if raw in ALIASES:
        return ALIASES[raw]
    if raw_ns in ALIASES:
        return ALIASES[raw_ns]

    # 2) 服装整码（完全 / 去空格连字符）
    if raw in APPAREL_SIZES:
        return raw
    if raw_ns in APPAREL_SIZES:
        return raw_ns

    # 3) 鞋类半码（兼容 UK/EU/US 前缀）
    m = RE_HALF.match(raw)
    if m:
        return m.group(1)  # 仅返回数字/半码，如 "7.5" 或 "10"

    # 4) EU 鞋码（35–48）：支持 "EU 40" / "EU40" / "40"
    if raw in EU_SHOE_RANGE:
        return raw
    if raw_ns.startswith("EU") and raw_ns[2:] in EU_SHOE_RANGE:
        return raw_ns[2:]

    # 5) 兜底：字符串包含标准服装码（如 "UK10" 含 "10"）
    for std in sorted(APPAREL_SIZES, key=lambda x: -len(x)):
        if std in raw_ns:
            return std

    return None

def clean_size_for_barbour(raw_size: str) -> str:
    """
    对外接口（兼容老名称）：
    - 能识别 → 返回统一规范值（如 2XL→XXL，UK 10→10）
    - 不能识别 → 返回原值（strip 后），并打印⚠️日志（不丢数据）
    """
    res = _clean_strict(raw_size)
    if res is None:
        out = (raw_size or "").strip()
        if out:  # 空字符串就不打日志了
            print(f"⚠️ 未识别尺码（保留原样）: {out}")
        return out
    return res

# 也导出一个直观别名，便于新代码调用
normalize_size_safe = clean_size_for_barbour
