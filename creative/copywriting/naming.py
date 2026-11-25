# -*- coding: utf-8 -*-
"""
短标题 / 宝贝名称：品牌 + 系列（款式）+ 商品名称，规则生成，结果稳定。

放不下时的取舍：品牌和商品名称始终保留，系列依次尝试
  英文带型号(SOFT7) → 英文主名(SOFT) → 中文名(柔酷) → 商品名称缩短后再试 → 去掉系列。
短标题有余量时加性别（男/女/儿童）。
"""
from __future__ import annotations

import re

from cfg.brand_strategy import BRAND_NAME_MAP
from cfg.creative_config import (
    ACCESSORY_RULES, BARBOUR_PREFIX_CATEGORY, CLOTHING_RULES, COPY_LIMITS, CREATIVE_BRAND_NAME,
    SERIES_STOP_WORDS, SHOE_BRANDS, SHOE_RULES, SMALL_ITEM_RULES,
)
from common.text.style_extractors import extract_style_name, strip_trademarks
from creative.copywriting.validator import text_length
from creative.product_source import ProductInfo

_CJK = re.compile(r"[一-鿿]+")
_BARBOUR_NOISE = re.compile(r"(?i)\b(?:barbour|international|b\.?intl|ladies|lady|(?:wo)?mens?)(?:['’]s)?\b")


def _compile(*groups):
    return [(re.compile(rf"(?<![a-z])(?:{p})(?![a-z])", re.IGNORECASE), cn) for g in groups for p, cn in g]


_SHOE_BRAND_RULES = _compile(SMALL_ITEM_RULES, SHOE_RULES, ACCESSORY_RULES)
_CLOTHING_BRAND_RULES = _compile(SMALL_ITEM_RULES, ACCESSORY_RULES, CLOTHING_RULES, SHOE_RULES)

# 这些系列的第一个词太泛，主名取前两个词
_TWO_WORD_HEADS = {"METROPOLE", "CODE", "ATL", "CITY", "DRESS", "URBAN"}


def brand_name(brand: str) -> str:
    en, cn = BRAND_NAME_MAP.get(brand, (brand.upper(), ""))
    return CREATIVE_BRAND_NAME.get(brand) or cn or en


def _url_series(url: str) -> str:
    """Camper 链接 .../shoes/romeo/camper-romeo_vulcanizado-36640-001 → Romeo（标题缺系列名时用）。"""
    m = re.search(r"/([^/]+)/camper-[^/]+$", url or "")
    return m.group(1).replace("_", " ").title() if m else ""


def _match_category(brand: str, text: str) -> str:
    for rx, cn in (_SHOE_BRAND_RULES if brand in SHOE_BRANDS else _CLOTHING_BRAND_RULES):
        if rx.search(text or ""):
            return cn
    return ""


def extract_series(p: ProductInfo) -> str:
    """系列英文名（可能含型号，如 SOFT 7）；识别不出返回空。"""
    if p.brand == "toast":   # Toast 标题是纯描述（Cotton Needlecord Shirt），没有系列名
        return ""
    title = strip_trademarks(p.title)
    if p.brand == "barbour":
        title = _BARBOUR_NOISE.sub(" ", title)
    s = extract_style_name(p.brand, title, "")
    s = _CJK.split(s)[0].strip(" .,+-")   # ECCO 会带中文系列名（LIVA 35 丽芙35），只留英文
    if p.brand == "camper" and s.lower() in SERIES_STOP_WORDS | {""}:
        s = _url_series(p.url)
    toks = s.split()
    while toks and toks[0].lower() in SERIES_STOP_WORDS:
        if p.brand == "ecco" and toks[0].lower() == "classic":   # ECCO CLASSIC 是系列名
            break
        toks.pop(0)
    # 系列名里混进品类词时截断（Evie Shirt → Evie）
    if p.brand in ("barbour", "clarks"):
        cut = next((i for i, t in enumerate(toks) if (i or p.brand == "barbour") and _match_category(p.brand, t)), len(toks))
        toks = toks[:cut]
    return " ".join(toks).strip(" .,+-")


def series_core(series: str) -> str:
    """系列主名（大写），用于中文名对照：SOFT 7 TRED → SOFT；Un Maui Lace → UN MAUI。"""
    toks = [t.strip(".,") for t in series.upper().split()]
    if not toks:
        return ""
    if len(toks) > 1 and (toks[0] in _TWO_WORD_HEADS or (len(toks[0]) <= 2 and toks[0] != "MX")):
        return " ".join(toks[:2])
    return toks[0]


def infer_category(p: ProductInfo, series: str) -> str:
    title = strip_trademarks(p.title)
    if p.brand == "geox":
        title = title.split("|")[0]
    if series and p.brand in SHOE_BRANDS:  # 去掉系列名，避免 Runner / Court / Desert 干扰
        stripped = re.sub(re.escape(series), " ", title, flags=re.IGNORECASE)
    else:
        stripped = title
    if p.brand == "barbour":
        return (_match_category(p.brand, stripped) or BARBOUR_PREFIX_CATEGORY.get(p.product_code[1:3].upper(), "")
                or _match_category(p.brand, p.style_category) or "服饰")
    cat = _match_category(p.brand, stripped) or _match_category(p.brand, re.sub(r"\bwear\b", "", p.style_category))
    return cat or ("休闲鞋" if p.brand in SHOE_BRANDS else "服饰")


def gender_word(p: ProductInfo) -> str:
    if re.search(r"\bunisex\b", p.title, re.IGNORECASE):
        return ""
    g = (p.gender or "").lower()
    if "童" in g or re.search(r"\b(kids?|child|children|boys?|girls?|junior|baby)\b", g):
        return "儿童"
    if "女" in g or re.search(r"\bwom[ae]n", g):
        return "女"
    if "男" in g or re.search(r"\bm[ae]n", g):
        return "男"
    return ""


def _series_options(series_en: str, core: str, series_cn: str) -> list[str]:
    first2 = "".join(series_en.split()[:2])
    opts = [first2] if re.search(r"\d", first2) else []   # SOFT 7 → SOFT7：带型号才用两段
    opts += [core.replace(" ", ""), series_cn]
    return list(dict.fromkeys(o for o in opts if o))


def _short_category(cat: str) -> str:
    """放不下系列名时的短写：切尔西靴 → 短靴，蜡棉夹克 → 夹克。"""
    if cat in ("切尔西靴", "马丁靴", "沙漠靴"):
        return "短靴"
    if len(cat) > 2 and cat.endswith("夹克"):
        return "夹克"
    return {"布洛克鞋": "皮鞋", "玛丽珍鞋": "单鞋"}.get(cat, cat)


def _join(brand_cn: str, series: str, gender: str, cat: str) -> str:
    # 系列名已带品类字时不重复（沙漠靴 + 短靴）
    if series and series[-1] in "鞋靴" and cat[-1:] == series[-1]:
        return f"{brand_cn}{gender}{series}"
    return f"{brand_cn}{series}{gender}{cat}"


def _compose(limit: int, brand_cn: str, series_opts: list[str], gender: str, cat: str) -> str:
    cats = list(dict.fromkeys([cat, _short_category(cat)]))
    for opts in (series_opts, [""]):
        for c in cats:
            for s in opts:
                for g in dict.fromkeys([gender, ""]):
                    name = _join(brand_cn, s, g, c)
                    if text_length(name) <= limit:
                        return name
    return ""   # 由 service 提示人工处理


def build_names(p: ProductInfo, series_en: str, series_cn: str, category_cn: str) -> dict[str, str]:
    b = brand_name(p.brand)
    opts = _series_options(series_en, series_core(series_en), series_cn)
    return {
        "short_title": _compose(COPY_LIMITS["short_title"], b, opts, gender_word(p), category_cn),
        "item_name": _compose(COPY_LIMITS["item_name"], b, opts, "", category_cn),
    }
