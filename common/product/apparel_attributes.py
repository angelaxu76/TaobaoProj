# -*- coding: utf-8 -*-
"""
从商品 TXT 的英文文案推断服装发布属性（面料 / 衣门襟 / 领口设计）。

三个函数识别不出时都返回 ""，由调用方回退到默认值。
"""
from __future__ import annotations

import re

# 成分段落里这些部位不算主面料（"100% cotton; Lining: 100% cotton"）
_NON_MAIN_PART = re.compile(
    r"\b(lining|wadding|padding|filling|trim|trimmings?|embroidery|strap|pockets?|cuffs?|hardware)\b",
    re.I,
)

# 顺序敏感：先匹配更具体的词（cashmere / alpaca 要先于 wool）
_FABRIC_MAP = [
    (r"cashmere", "羊绒"),
    (r"alpaca", "羊驼毛"),
    (r"mohair", "马海毛"),
    (r"merino|wool|lambswool", "羊毛"),
    (r"linen|flax", "亚麻"),
    (r"hemp", "大麻"),
    (r"silk", "桑蚕丝"),
    (r"cotton", "棉"),
    (r"viscose|rayon", "粘胶纤维"),
    (r"lyocell|tencel", "莱赛尔"),
    (r"polyamide|nylon", "锦纶"),
    (r"polyester", "涤纶"),
    (r"acrylic", "腈纶"),
    (r"leather", "皮革"),
]

# 下装没有领型；配饰既没有领型也没有门襟
_BOTTOMS = {"trousers", "jeans", "skirts", "shorts", "culottes"}
_ACCESSORIES = {
    "socks", "jewellery", "scarves", "bags", "hats", "gloves", "belts", "tights",
}

# 顺序敏感："high round neckline" 应判圆领，所以圆领在高领之前
_NECKLINE_MAP = [
    (r"\bv[- ]?neck", "V领"),
    (r"\bboat[- ]?neck", "一字领"),
    (r"\bsquare[- ]?neck", "方领"),
    (r"\b(?:band|grandad|stand|mandarin)[- ]collar", "立领"),
    (r"\bhood(?:ed|ie)?\b", "连帽"),
    (r"\blapels?\b", "西装领"),
    (r"\b(?:crew|round|rounded|scoop|almond|ribbed)[, -]+(?:ribbed )?neck", "圆领"),
    (r"\b(?:high|roll|rolled|polo|turtle|funnel|mock)(?:[- ]edged?)?[- ]?neck", "高领"),
    (r"\bcollar", "翻领"),
]

# 这些部位上的扣子 / 拉链只是装饰或口袋，不是门襟
_NOT_PLACKET = re.compile(
    r"\b(cuffs?|pockets?|tabs?|flaps?|hems?|sleeves?|nape|neck|shoulders?|back|side openings?)\b"
)


def _split_clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[.|,;]", text.lower()) if c.strip()]


def extract_fabric(material: str) -> str:
    """取主面料含量最高的成分，如 "47% wool, 42% cotton" → 羊毛。"""
    material = (material or "").strip()
    if not material or material.lower() == "no data":
        return ""

    parts = [p for p in material.split(";") if p.strip()]
    main = next((p for p in parts if not _NON_MAIN_PART.search(p)), parts[0])

    components = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*([^,;%]+)", main)
    if components:
        name = max(components, key=lambda c: float(c[0]))[1]
    else:
        name = main

    for pattern, fabric in _FABRIC_MAP:
        if re.search(pattern, name, re.I):
            return fabric
    return ""


def extract_closure(style_category: str, *texts: str) -> str:
    """按文案判断门襟；texts 按可信度从高到低传入。"""
    if (style_category or "").strip().lower() in _ACCESSORIES:
        return ""

    for text in texts:
        clauses = _split_clauses(text or "")
        placket = [c for c in clauses if not _NOT_PLACKET.search(c)]

        if any(re.search(r"\bdouble[- ]breasted\b", c) for c in clauses):
            return "双排扣"
        if any(re.search(r"\b(?:zip|zipped|zipper)\b", c) for c in placket):
            return "拉链"
        if any(re.search(r"\bbuttons?\b|\bbutton[- ]?(?:through|front|placket)\b", c) for c in placket):
            return "单排扣"
        if any(re.search(r"\bwrap\b|\btie waist\b", c) for c in placket):
            return "系带"
        if any(re.search(r"\bpull[- ]on\b|\b(?:elasticated|drawstring|drawcord)\b.*\bwaist\b", c) for c in placket):
            return "松紧"
    return ""


def extract_neckline(style_category: str, *texts: str) -> str:
    """按文案判断领型；texts 按可信度从高到低传入。"""
    cat = (style_category or "").strip().lower()
    if cat in _BOTTOMS or cat in _ACCESSORIES:
        return ""

    for text in texts:
        blob = (text or "").lower()
        for pattern, neckline in _NECKLINE_MAP:
            if re.search(pattern, blob):
                return neckline
    return ""
