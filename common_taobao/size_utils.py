# -*- coding: utf-8 -*-
"""
clean_size_for_barbour: Barbour/服装优先的尺码清洗与归一化
"""

from __future__ import annotations
import re
from typing import Optional

ALIASES = {
    "1XL": "XL",
    "2XL": "XXL",
    "3XL": "XXXL",
    "4XL": "XXXXL",
    "5XL": "XXXXXL",
    "6XL": "XXXXXXL",
    "XS": "XS",
    "2XS": "XXS",
    "XXS": "XXS",
    "3XS": "XXXS",
    "XXXS": "XXXS",
    "XSMALL": "XS",
    "X-SMALL": "XS",
    "X SMALL": "XS",
    "SMALL": "S",
    "MEDIUM": "M",
    "LARGE": "L",
    "X-LARGE": "XL",
    "XLARGE": "XL",
    "X LARGE": "XL",
    "ONE SIZE": "ONESIZE",
    "ONE-SIZE": "ONESIZE",
    "ONESIZE": "ONESIZE",
    "O/S": "ONESIZE",
    "OS": "ONESIZE",
    "OSFM": "ONESIZE",
    "FREE SIZE": "ONESIZE",
    "FREESIZE": "ONESIZE",
    "F/S": "ONESIZE",
    # 新增 Unknown 映射
    "UNKNOWN": "Unknown",
    "UK UNKNOWN": "Unknown",
}

APPAREL_SIZES = {
    "XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL",
    "XXXXL", "XXXXXL", "XXXXXXL", "ONESIZE",
    *{str(s) for s in range(4, 24, 2)},
    *{str(s) for s in range(30, 56, 2)},
}

EU_SHOE_RANGE = {str(s) for s in range(35, 49)}

# 修改：允许从 1 开始
RE_HALF = re.compile(r"^(?:UK|EU|US)?\s*([1-9](?:\.5)?|1[0-5](?:\.5)?)$", flags=re.IGNORECASE)

def _norm(s: str) -> str:
    return (s or "").strip().upper()

def _squash(s: str) -> str:
    return _norm(s).replace(" ", "").replace("-", "")

def _clean_strict(raw_size: str) -> Optional[str]:
    if not raw_size:
        return None
    raw = _norm(raw_size)
    raw_ns = _squash(raw_size)
    if raw in ALIASES: return ALIASES[raw]
    if raw_ns in ALIASES: return ALIASES[raw_ns]
    if raw in APPAREL_SIZES: return raw
    if raw_ns in APPAREL_SIZES: return raw_ns
    m = RE_HALF.match(raw)
    if m: return m.group(1)
    if raw in EU_SHOE_RANGE: return raw
    if raw_ns.startswith("EU") and raw_ns[2:] in EU_SHOE_RANGE:
        return raw_ns[2:]
    for std in sorted(APPAREL_SIZES, key=lambda x: -len(x)):
        if std in raw_ns: return std
    return None

def clean_size_for_barbour(raw_size: str) -> str:
    s = (raw_size or "").strip()
    if not s:
        return ""
    up = " ".join(s.split()).upper()
    if up in {"UNKNOWN", "UK UNKNOWN"}:
        return "Unknown"
    res = _clean_strict(s)
    if res is None:
        print(f"⚠️ 未识别尺码（保留原样）: {s}")
        return s
    return res

normalize_size_safe = clean_size_for_barbour
