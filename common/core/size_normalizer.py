# -*- coding: utf-8 -*-
# common/core/size_normalizer.py

import re
from collections import OrderedDict
from typing import Iterable, Tuple, Dict, Any, Optional

# ========== 标准尺码序 ==========
WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30,32,...,50

# 字母尺码映射
ALPHA_MAP = {
    "xxxs": "2XS", "2xs": "2XS",
    "xxs": "XS", "xs": "XS",
    "s": "S", "sm": "S", "small": "S",
    "m": "M", "md": "M", "medium": "M",
    "l": "L", "lg": "L", "large": "L",
    "xl": "XL", "x-large": "XL", "x large": "XL",
    "xxl": "2XL", "2xl": "2XL",
    "xxxl": "3XL", "3xl": "3XL",
}

# ========== Barbour 编码前缀 → 性别/大类（仅用于性别、服装/配件粗判）==========
# 备注：Barbour 常见前缀：M* 男、L* 女；童装/狗类/配件另行补充。
BARBOUR_GENDER_BY_PREFIX = {
    # Men
    "MWX": "男款", "MQU": "男款", "MLI": "男款", "MSH": "男款",
    "MKN": "男款", "MTS": "男款", "MPQ": "男款",
    # Women
    "LWX": "女款", "LQU": "女款", "LLI": "女款", "LSH": "女款",
    "LKN": "女款", "LTS": "女款",
    # Junior/Kids（如遇真实样本再补充前缀）
    # "BKN": "童款", ...
}

# 标题/描述中的性别关键词
GENDER_KEYWORDS = [
    (re.compile(r"\b(women'?s|ladies|female)\b", re.I), "女款"),
    (re.compile(r"\b(men'?s|gents|male)\b", re.I), "男款"),
    (re.compile(r"\b(girl|boy|junior|kid|youth)\b", re.I), "童款"),
    (re.compile(r"\b(unisex)\b", re.I), "中性"),
]

def _clean_size_token(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s*\(.*?\)\s*", "", s)  # 去 "(UK 10-12)" 等括号内容
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace("uk ", "").replace("eu ", "").replace("us ", "")
    s = s.replace("chest ", "").replace("waist ", "")
    s = s.replace('in', '').replace('"', '')
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_barbour_size(gender: str, raw_size: str) -> Optional[str]:
    """
    将站点抓到的原始尺码归一化为你的标准：
      - 女款：4/6/8/10/12/14/16/18/20
      - 男款(字母)：2XS/XS/S/M/L/XL/2XL/3XL
      - 男款(数字)：30/32/.../50
    返回 None 表示无法识别（上层可选择丢弃或记录日志）
    """
    if not raw_size:
        return None

    g = (gender or "").strip()
    token = _clean_size_token(raw_size)

    # 1) 纯字母（small/medium/xxl…）
    if re.fullmatch(r"[a-z\s\-]+", token):
        key = token.replace("-", " ").strip()
        key = ALPHA_MAP.get(key, ALPHA_MAP.get(key.replace(" ", ""), None))
        if key and key in MEN_ALPHA_ORDER:
            return key

    # 2) 数字抽取
    nums = re.findall(r"\d{1,3}", token)
    if nums:
        n = int(nums[0])

        # 女款典型：4–20 偶数
        if n in {4,6,8,10,12,14,16,18,20}:
            return str(n)
        # 男款典型：30–50 偶数（腰围/胸围型）
        if 28 <= n <= 52 and n % 2 == 0:
            return str(n)

        # 模糊对齐（可选）
        if g == "女款" and 2 <= n <= 22:
            nearest = min(WOMEN_ORDER, key=lambda x: abs(int(x)-n))
            return nearest
        if g == "男款":
            if 28 <= n <= 54:
                candidate = n if n % 2 == 0 else n-1
                candidate = max(30, min(50, candidate))
                return str(candidate)

    # 3) 简写字母兜底
    short = token.replace(" ", "")
    if short in ALPHA_MAP and ALPHA_MAP[short] in MEN_ALPHA_ORDER:
        return ALPHA_MAP[short]

    return None

def sort_size_keys_for_gender(keys: Iterable[str], gender: str) -> list:
    """按你的约定顺序对尺码 key 排序。"""
    def key_fn(k):
        if gender == "女款" and k in WOMEN_ORDER:
            return (0, WOMEN_ORDER.index(k))
        if gender == "男款" and k in MEN_ALPHA_ORDER:
            return (1, MEN_ALPHA_ORDER.index(k))
        if gender == "男款" and k in MEN_NUM_ORDER:
            return (2, MEN_NUM_ORDER.index(k))
        return (9, k)
    return sorted(keys, key=key_fn)

def build_size_fields_from_offers(
    offer_list: Iterable[Tuple[str, Any, Any, Any]],
    gender: str
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], str]:
    """
    输入: offer_list = [(size, price, stock_status, can_order), ...]
    输出: (SizeMap, SizeDetail, Product Size)
      - SizeMap: { "M": "有货", "L": "无货", ... }
      - SizeDetail: { "M": {"stock_count": 1, "ean": "0000000000000"}, ... }
      - Product Size: "M:有货;L:无货;..."
    规则：同尺码重复出现时，“有货优先”覆盖。
    """
    norm_map = OrderedDict()
    detail_map = OrderedDict()

    for raw_size, price, stock_status, can_order in (offer_list or []):
        norm = normalize_barbour_size(gender, raw_size)
        if not norm:
            continue
        curr = "有货" if bool(can_order) else "无货"
        prev = norm_map.get(norm)
        if prev is None or (prev == "无货" and curr == "有货"):
            norm_map[norm] = curr
            detail_map[norm] = {
                "stock_count": 1 if can_order else 0,
                "ean": "0000000000000",
            }

    ordered_keys = sort_size_keys_for_gender(norm_map.keys(), gender)
    size_map = {k: norm_map[k] for k in ordered_keys}
    size_detail = {k: detail_map[k] for k in ordered_keys}
    product_size = ";".join(f"{k}:{size_map[k]}" for k in ordered_keys)
    return size_map, size_detail, product_size

# ========== 性别判定 ==========
def _barbour_gender_from_code(product_code: str) -> Optional[str]:
    if not product_code:
        return None
    m = re.match(r"([A-Z]{3})", product_code.upper())
    if not m:
        return None
    prefix = m.group(1)
    # M* → 男款；L* → 女款；匹配不到按映射表
    if prefix.startswith("M"):
        return "男款"
    if prefix.startswith("L"):
        return "女款"
    return BARBOUR_GENDER_BY_PREFIX.get(prefix)

def _gender_from_text(text: str) -> Optional[str]:
    t = text or ""
    for pat, label in GENDER_KEYWORDS:
        if pat.search(t):
            return label
    return None

def unify_gender_label(gender: Optional[str]) -> Optional[str]:
    if not gender:
        return None
    g = gender.strip().lower()
    if g in {"男", "man", "men", "men's", "mens", "male", "gents"}:
        return "男款"
    if g in {"女", "woman", "women", "women's", "ladies", "female"}:
        return "女款"
    if g in {"kid", "kids", "boy", "girl", "junior", "youth", "童"}:
        return "童款"
    if g in {"unisex", "中性"}:
        return "中性"
    # 已是标准中文
    if gender in {"男款", "女款", "童款", "中性"}:
        return gender
    return None

def infer_gender_for_barbour(
    product_code: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    given_gender: Optional[str] = None
) -> Optional[str]:
    """
    性别判定优先级（Barbour）：
      1) Product Code 前缀（M*→男款，L*→女款；或映射表命中）
      2) 标题/描述关键词（women's/men's/junior/unisex）
      3) 传入的 given_gender（若以上都无）
    """
    # 1) 代码前缀（最稳）
    g1 = _barbour_gender_from_code(product_code or "")
    if g1:
        return g1

    # 2) 标题/描述关键词
    g2 = _gender_from_text(f"{title or ''} {description or ''}")
    if g2:
        return g2

    # 3) 来自上游的 gender 标准化
    g3 = unify_gender_label(given_gender)
    if g3:
        return g3

    return None
