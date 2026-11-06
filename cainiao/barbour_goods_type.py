# -*- coding: utf-8 -*-
"""
Barbour 菜鸟货品：按商品类型逐步匹配 → 中文货品名称 + 包装尺寸重量。

匹配顺序（越靠前越可靠）：
  1) 编码前缀命中 ACCESSORY_PREFIX_RULES（帽子/包/围巾…）
       → 英文名 style_name 按配件 CATEGORY_RULES 识别具体品类（平顶帽/毛线帽…）
       → 识别不到用前缀默认品类
  2) 编码前缀命中 CODE_PREFIX_RULES（服装）
       → 英文名按 CLOTHING_STYLE_MAP 识别 → 识别不到用前缀默认品类
  3) 前缀未知：英文名先试配件规则，再试服装关键词，再试 DB category，最后兜底 "服装"

注意：barbour_products.category 不可靠（如 "Waxed Flat Cap" 被标成 waxed jacket），
所以只在最后一步使用；barbour_products.title 基本为空，英文名在 style_name。
"""
import re
from typing import Dict, Tuple

from config import BRAND_CONFIG
from brands.barbour.common.generate_taobao_title_accessories import CATEGORY_RULES

_cfg = BRAND_CONFIG.get("barbour", {})
ACCESSORY_PREFIX_RULES = _cfg.get("ACCESSORY_PREFIX_RULES", {})
CODE_PREFIX_RULES = _cfg.get("CODE_PREFIX_RULES", {})

# 商品大类
TYPE_CLOTHING = "服装"

# 服装英文关键词 → 中文款式（按 key 长度倒序匹配，避免 "shirt" 抢 "t-shirt"）
CLOTHING_STYLE_MAP = {
    # 外套
    "t-shirt": "T恤", "tee": "T恤",
    "wax": "蜡棉夹克", "jacket": "夹克",
    "quilt": "菱格夹克", "puffer": "羽绒服",
    "gilet": "马甲", "vest": "马甲", "waistcoat": "马甲", "liner": "内胆",
    "coat": "大衣", "overcoat": "大衣", "peacoat": "大衣",
    "parka": "派克", "anorak": "防风外套", "blazer": "西装外套",
    # 上装
    "overshirt": "衬衫", "shirt": "衬衫", "polo": "POLO衫",
    "sweat": "卫衣", "hoodie": "卫衣",
    "knit": "针织衫", "sweater": "毛衣", "jumper": "毛衣", "cardigan": "开衫",
    "fleece": "抓绒",
    # 下装
    "trouser": "长裤", "jean": "牛仔裤", "legging": "打底裤",
    "shorts": "短裤", "chino short": "短裤", "cargo short": "短裤", "swim short": "泳裤",
    # 其他
    "shirt-dress": "衬衫裙", "dress": "连衣裙", "skirt": "半身裙",
}

# 包装尺寸/重量（长宽高 mm，重量 g）。按大类配置，未配置的走 _DEFAULT_PACKAGE。
_DEFAULT_PACKAGE = {"长": 400, "宽": 300, "高": 70, "毛重": 1200, "净重": 900}
PACKAGE_SPEC_BY_TYPE: Dict[str, Dict[str, int]] = {
    TYPE_CLOTHING: _DEFAULT_PACKAGE,
    "帽子": {"长": 300, "宽": 250, "高": 120, "毛重": 400, "净重": 200},
}
PACKAGE_SPEC_BY_TYPE["兜帽"] = PACKAGE_SPEC_BY_TYPE["帽子"]


def _prefix(code: str) -> str:
    return (code or "").strip().upper()[:3]


def _match_accessory(text: str) -> Tuple[str, str]:
    """英文名 → (配件大类, 中文品类)，如 ("帽子", "平顶帽")；未命中返回 ("", "")"""
    t = (text or "").lower()
    for pat, words, group in CATEGORY_RULES:
        if re.search(pat, t):
            return group, words[0]
    return "", ""


def _match_clothing(text: str) -> str:
    t = (text or "").lower()
    for k in sorted(CLOTHING_STYLE_MAP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}", t):
            return CLOTHING_STYLE_MAP[k]
    return ""


def _gender_label(goods_type: str, gender: str, prefix_gender: str = "") -> str:
    """服装：男装/女装；配件：男士/女士/男女同款（优先 DB 性别，其次前缀规则）"""
    g = (gender or "").lower()
    is_female = "女" in g or bool(re.search(r"\b(women|womens|women's|ladies|lady|female)\b", g))
    is_male = not is_female and ("男" in g or bool(re.search(r"\b(men|mens|men's|male)\b", g)))
    if goods_type == TYPE_CLOTHING:
        return "女装" if is_female else "男装" if is_male else ""
    if prefix_gender:
        return prefix_gender
    return "女士" if is_female else "男士" if is_male else ""


def classify_barbour_goods(code: str, style_name: str = "", gender: str = "",
                           category: str = "") -> Tuple[str, str, str]:
    """
    返回 (goods_type, gender_label, style_zh)
      goods_type: "服装" / "帽子" / "包" / "围巾" ...（对应 PACKAGE_SPEC_BY_TYPE 的 key）
    """
    prefix = _prefix(code)

    # 1) 配件前缀
    if prefix in ACCESSORY_PREFIX_RULES:
        prefix_gender, default_cat = ACCESSORY_PREFIX_RULES[prefix]
        group, style_zh = _match_accessory(style_name)
        goods_type = group or default_cat
        return goods_type, _gender_label(goods_type, gender, prefix_gender), style_zh or default_cat

    # 2) 服装前缀
    if prefix in CODE_PREFIX_RULES:
        _, default_style = CODE_PREFIX_RULES[prefix]
        style_zh = _match_clothing(style_name)
        # 只匹配到泛称 "夹克" 时，前缀品类更具体（蜡棉夹克/绗缝夹克/防水夹克…）
        if not style_zh or style_zh == "夹克":
            style_zh = default_style
        return TYPE_CLOTHING, _gender_label(TYPE_CLOTHING, gender), style_zh

    # 3) 前缀未知：英文名 → 配件 → 服装 → category → 兜底
    group, style_zh = _match_accessory(style_name)
    if group:
        return group, _gender_label(group, gender), style_zh
    style_zh = _match_clothing(style_name) or _match_clothing(category) or "服装"
    return TYPE_CLOTHING, _gender_label(TYPE_CLOTHING, gender), style_zh


def build_barbour_goods_name(code: str, size: str, style_name: str = "", gender: str = "",
                             category: str = "", brand_label: str = "Barbour") -> Tuple[str, str]:
    """返回 (货品名称, goods_type)，如 ("Barbour男士平顶帽MHA0439GY31尺码ONESIZE", "帽子")"""
    goods_type, gender_label, style_zh = classify_barbour_goods(code, style_name, gender, category)
    return f"{brand_label}{gender_label}{style_zh}{code}尺码{size}", goods_type


def get_package_spec(goods_type: str) -> Dict[str, int]:
    return PACKAGE_SPEC_BY_TYPE.get(goods_type, _DEFAULT_PACKAGE)
