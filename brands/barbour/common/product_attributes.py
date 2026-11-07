# -*- coding: utf-8 -*-
"""
识别 Barbour 商品的"商品类型"和"商品材质"，用于发布 Excel 的属性列。

与标题生成的区别：
  - 标题里的品类词是搜索词（如"翻领T恤POLO衫"、"加厚衬衫外套夹克"），
    这里输出的是规范的类型名（"POLO衫"、"衬衫外套"）。
  - 标题里的材质混有工艺/图案（绗缝、格纹、针织），这里只输出面料成分（棉、尼龙……）。

材质是对买家的属性声明，识别不出时返回空字符串，不做猜测。
"""
import re
from typing import List, Optional, Tuple

from brands.barbour.common.generate_taobao_title_accessories import (
    ACCESSORY_PREFIX_RULES,
    detect_categories,
)
from brands.barbour.common.generate_taobao_title_v2 import (
    CODE_PREFIX_RULES,
    FOOTWEAR_RULES,
    refine_type_by_keywords,
)


# ==== 商品类型 ====
# 标题品类词 → 规范类型名
TYPE_NORMALIZE = {
    "蜡棉夹克": "油蜡夹克",
    "翻领T恤POLO衫": "POLO衫",
    "加厚衬衫外套夹克": "衬衫外套",
    "翻领薄衬衫": "衬衫",
    "中长连衣裙": "连衣裙",
    "中长裙": "半身裙",
    "针织": "毛衣",
}

# 只由前缀决定的品类
FIXED_TYPES = {
    "MSE": "太阳镜", "LSE": "太阳镜",
    "MLF": "香水", "LLF": "香水",
}

# 这些词不会出现在配色名里，可以在对应前缀内放心按商品名细分
# （"trench" 之类会出现在配色名里，已由 refine_type_by_keywords 限定前缀处理）
JACKET_PREFIXES = {"MWX", "LWX", "MQU", "LQU", "MCA", "LCA", "MWB", "LWB", "MSP", "LSP"}
PREFIX_REFINE_RULES: List[Tuple[set, str, str]] = [
    (JACKET_PREFIXES, r"\b(gilet|waistcoat|bodywarmer)\b", "马甲"),
    (JACKET_PREFIXES, r"\bparka\b", "派克大衣"),
    ({"MKN", "LKN"}, r"\bcardigan\b", "开衫"),
    ({"MKN", "LKN"}, r"\b(vest|tank|tabard)\b", "针织背心"),
    ({"MKN", "LKN"}, r"\bpolo\b", "针织POLO衫"),
    ({"MOL", "LOL"}, r"\bhood(ed|ie)?\b", "连帽卫衣"),
]

# 配件标题规则未细分的包款
BAG_EXTRA_RULES: List[Tuple[str, str]] = [
    (r"\bsatchel\b", "斜挎包"),
    (r"\bshopper\b|\bbeach\s+bag\b", "手提包"),
    (r"\bcarry[\s-]?all\b|\bflight\s+bag\b|\bgym\s+bag\b", "旅行包"),
]
# 标题里用"托特包"（搜索词），类型列归到"手提包"
ACCESSORY_TYPE_ALIAS = {"托特包": "手提包"}

# 前缀无法判断时（如 6 位数字编码），只看商品名里 " - 配色" 之前的部分
NAME_ONLY_RULES: List[Tuple[str, str]] = [
    (r"\bgilet\b|\bwaistcoat\b|\bbodywarmer\b", "马甲"),
    (r"\bwax(ed)?\b.*\bjacket\b", "油蜡夹克"),
    (r"\bquilt(ed)?\b.*\bjacket\b", "绗缝夹克"),
    (r"\bparka\b", "派克大衣"),
    (r"\bfleece\b", "抓绒夹克"),
    (r"\bovershirt\b", "衬衫外套"),
    (r"\bhood(ie|ed\s+sweat)", "连帽卫衣"),
    (r"\bsweat(shirt)?\b", "卫衣"),
    (r"\bcardigan\b", "开衫"),
    (r"\bjumper\b|\bsweater\b|\bknit(ted)?\b", "毛衣"),
    (r"\bpolo\b", "POLO衫"),
    (r"\bt-?shirt\b|\btee\b", "T恤"),
    (r"\bshirt\b", "衬衫"),
    (r"\bdress\b", "连衣裙"),
    (r"\bskirt\b", "半身裙"),
    (r"\bjeans?\b", "牛仔裤"),
    (r"\btrousers?\b|\bchinos?\b", "休闲裤"),
    (r"\bshorts?\b", "短裤"),
    (r"\bcoat\b", "大衣"),
    (r"\bjacket\b", "夹克"),
]


def _accessory_type(code: str, style_name: str, default: str) -> str:
    core, _extra, _group = detect_categories(code, style_name)
    if "礼盒" in core:  # 帽子+围巾这类组合装，按礼盒算
        return "礼盒"
    first = core[0] if core else default
    if first == "包":
        for pat, zh in BAG_EXTRA_RULES:
            if re.search(pat, style_name, re.I):
                return zh
    return ACCESSORY_TYPE_ALIAS.get(first, first)


def detect_product_type(code: str, style_name: Optional[str]) -> str:
    """返回商品类型；前缀和商品名都识别不出时返回空字符串。"""
    c = (code or "").upper().strip()
    name = style_name or ""
    prefix = c[:3]

    if prefix in FIXED_TYPES:
        return FIXED_TYPES[prefix]

    if prefix in ACCESSORY_PREFIX_RULES:
        return _accessory_type(c, name, ACCESSORY_PREFIX_RULES[prefix][1])

    if prefix in CODE_PREFIX_RULES:
        raw = refine_type_by_keywords(c, CODE_PREFIX_RULES[prefix][1], name)
        base = TYPE_NORMALIZE.get(raw, raw)
        for prefixes, pat, zh in PREFIX_REFINE_RULES:
            if prefix in prefixes and re.search(pat, name, re.I):
                return zh
        return base

    head = name.split(" - ")[0]
    for pat, zh in NAME_ONLY_RULES + FOOTWEAR_RULES:
        if re.search(pat, head, re.I):
            return zh
    return _accessory_type(c, head, "")


# ==== 商品材质 ====
FIBRES = {
    "cotton": "棉",
    "polyester": "聚酯纤维",
    "nylon": "尼龙",
    "polyamide": "尼龙",
    "wool": "羊毛",
    "lambswool": "羊毛",
    "merino": "羊毛",
    "cashmere": "羊绒",
    "linen": "亚麻",
    "viscose": "粘纤",
    "acrylic": "腈纶",
    "silk": "蚕丝",
    "leather": "真皮",
    "suede": "反绒皮",
    "polyurethane": "聚氨酯",
    "rubber": "橡胶",
    "lyocell": "莱赛尔",
    "tencel": "莱赛尔",
    "modal": "莫代尔",
    "elastane": "氨纶",
    "spandex": "氨纶",
}
_FIBRE_ALT = "|".join(sorted(FIBRES, key=len, reverse=True))

# 成分标签：外层面料 / 辅料。其余标签（如 Features:）不影响判断
OUTER_LABELS = {"outer", "shell", "main", "body", "fabric", "composition", "material",
                "materials", "exterior", "upper", "face"}
SECONDARY_LABELS = {"lining", "linings", "liner", "inner", "filling", "fill", "wadding",
                    "padding", "insulation", "trim", "trims", "collar", "cuff", "cuffs",
                    "rib", "sole", "outsole", "insole", "pocket", "pockets", "hood",
                    "sleeve", "sleeves", "contrast", "embroidery", "thread", "strap",
                    "straps", "handle", "handles", "patch", "binding"}
# 紧跟在材质词后面、说明它只是辅料的词（"100% cotton lining" / "leather trims"）
_SECONDARY_AFTER = re.compile(
    r"\s*(?:[a-z-]+\s+)?(lining|lined|linings|trim|trims|trimmed|filling|filled|wadding|"
    r"padding|collar|patch|patches|detail|details|detailing|sole|handles?|straps?|label|"
    r"badge|tab|tabs|binding)\b"
)

_PCT = re.compile(rf"(\d{{1,3}})\s*%\s*(?:[a-z-]+\s+){{0,2}}?({_FIBRE_ALT})\b")
_LABEL = re.compile(r"\b((?:[a-z]+\s+){0,3}[a-z]+)\s*:")
_MADE_FROM = re.compile(
    r"\b(?:made|crafted|constructed|cut|knitted|knit|woven|fashioned|manufactured|spun)\s+"
    r"(?:from|in|of|using|with)\s+(?:[a-z0-9'’-]+,?\s+){0,5}?"
    rf"({_FIBRE_ALT})\b"
)

# "cotton pique" / "wool-blend" 这类面料短语
_FABRIC_PHRASE = re.compile(
    rf"\b({_FIBRE_ALT})[\s-](?:blend|rich|mix|pique|piqué|jersey|twill|poplin|interlock|"
    r"canvas|fabric|yarn|flannel|oxford|drill|gabardine)\b"
)

# 商品名兜底。Barbour 的 "Wax Leather" 系列是蜡棉主体 + 皮革饰边，不是皮具；
# "faux fur" 多是内衬或饰边（如 Faux Fur Welly），不作为材质。
NAME_MATERIAL_RULES: List[Tuple[str, str]] = [
    (r"\bwax(ed)?\s+leather\b", "棉"),
    (r"\bfaux\s+leather\b", "人造革"),
    (r"\bleather\b(?!\s+trim)", "真皮"),
    (r"\bsuede\b(?!\s+trim)", "反绒皮"),
    (r"\bcashmere\b", "羊绒"),
    (r"\b(lambswool|merino|wool)\b", "羊毛"),
    (r"\blinen\b", "亚麻"),
    (r"\bcotton\b", "棉"),
    (r"\bnylon\b", "尼龙"),
    (r"\bpolyester\b", "聚酯纤维"),
    (r"\bwax(ed)?\b", "棉"),  # Barbour 的油蜡面料都是蜡棉
]


def _label_rank(text: str, pos: int) -> Optional[int]:
    """
    判断 pos 处的成分属于哪个标签：2=外层面料，1=无标签，None=辅料（应跳过）。
    只看同一句内最近的 "xxx:"，"Lining: 65% Polyester, 35% Cotton" 的两项都算里料。
    标签可以是多个词："Inner Main Fabric:" 算里料，"Outer and Inner:" 算外层。
    分号不算断句："Inner: Main body; 100% Polyamide / Collar; 100% Cotton" 全是里料。
    """
    window = text[max(0, pos - 160):pos]
    labels = list(_LABEL.finditer(window))
    if not labels:
        return 1
    last = labels[-1]
    if re.search(r"[.!?]\s", window[last.end():]):
        return 1
    words = set(last.group(1).split())
    if "outer" in words:
        return 2
    if words & SECONDARY_LABELS:
        return None
    return 2 if words & OUTER_LABELS else 1


def _material_from_percentages(descriptions: List[str]) -> str:
    best: Optional[Tuple[int, int]] = None
    best_zh = ""
    for text in descriptions:
        for m in _PCT.finditer(text):
            rank = _label_rank(text, m.start())
            if rank is None or _SECONDARY_AFTER.match(text, m.end()):
                continue
            score = (rank, int(m.group(1)))
            if best is None or score > best:
                best, best_zh = score, FIBRES[m.group(2)]
    return best_zh


def _material_from_phrases(descriptions: List[str]) -> str:
    for pattern in (_MADE_FROM, _FABRIC_PHRASE):
        for text in descriptions:
            for m in pattern.finditer(text):
                if not _SECONDARY_AFTER.match(text, m.end()):
                    return FIBRES[m.group(1)]
    return ""


def detect_material(style_name: Optional[str], descriptions: Optional[List[str]] = None) -> str:
    """
    返回主面料中文名，识别不出时返回空字符串。依次看：
      1. 描述里的百分比成分（外层标签优先，同级取占比最高，跳过里料/填充/饰边）
      2. 描述里的 "made from xxx" 句式和 "cotton pique" 这类面料短语
      3. 商品名里的材质词
    """
    texts = [d.lower() for d in (descriptions or []) if d]
    zh = _material_from_percentages(texts) or _material_from_phrases(texts)
    if zh:
        return zh
    for pat, name_zh in NAME_MATERIAL_RULES:
        if re.search(pat, style_name or "", re.I):
            return name_zh
    return ""
