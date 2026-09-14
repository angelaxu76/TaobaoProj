# -*- coding: utf-8 -*-
"""
生成 Barbour 配件类（包/帽子/围巾/皮带等）淘宝标题。

与 generate_taobao_title_v2.py（服装/夹克类）结构一致，但品类判定前缀表、
卖点/噪声/系列词表是配件专属的一套，两边互不影响。通用算法（字节长度计算、
颜色映射、系列名提取、60字节补齐框架）来自 title_shared.py，两边共用。
"""
import re
from typing import Tuple

from config import BRAND_CONFIG, BRAND_NAME_MAP
from common.text.translate import safe_translate
from common.text.ad_sanitizer import sanitize_text
from common.utils.logger_utils import setup_logger
from brands.barbour.common.title_shared import (
    get_byte_length,
    map_color,
    detect_material_cn as _detect_material_cn,
    detect_keyword_tags as _detect_keyword_tags,
    detect_series as _detect_series,
    pad_to_60_bytes as _pad_to_60_bytes,
)

logger = setup_logger("barbour_taobao_title_accessories")

# ==== 前缀规则（配件品类，见 cfg/brands/barbour.py ACCESSORY_PREFIX_RULES）====
_cfg = BRAND_CONFIG.get("barbour") or BRAND_CONFIG.get("Barbour") or {}
ACCESSORY_PREFIX_RULES = _cfg.get("ACCESSORY_PREFIX_RULES", {})


# ==== 材质提示（配件专用：皮革/帆布/羊毛围巾等，与夹克的蜡棉/绗缝不同）====
MATERIAL_HINTS = [
    (r"\bleather\b", "皮革"),
    (r"\bsuede\b", "反绒皮"),
    (r"\bcanvas\b", "帆布"),
    (r"\bwax(ed)?\b", "蜡棉"),
    (r"\bwool\b", "羊毛"),
    (r"\bcashmere\b", "羊绒"),
    (r"\btartan\b", "苏格兰格纹"),
    (r"\bcotton\b", "棉质"),
    (r"\bknit(ted)?\b", "针织"),
]


def detect_material_cn(style_name_en: str) -> str:
    return _detect_material_cn(style_name_en, MATERIAL_HINTS)


# ==== 卖点按类型 ====
TYPE_EXTRAS = {
    "包": ["英伦风", "百搭", "通勤", "日常出行"],
    "帽子": ["英伦风", "百搭", "保暖", "秋冬"],
    "兜帽": ["可拆卸", "百搭", "秋冬"],
    "皮带": ["英伦风", "百搭", "商务休闲"],
    "围巾": ["英伦风", "保暖", "百搭", "秋冬"],
}

# ==== 核心品类关键词（近义词，帮助多接住一批搜索流量）====
TYPE_CORE_KEYWORDS = {
    "包": ["手提包"],
    "帽子": ["鸭舌帽"],
    "围巾": ["披肩"],
}

# ==== 关键词映射（优先用于补齐 60 字节）====
KEYWORD_MAP = {
    "tartan": "格纹",
    "check": "格纹",
    "waxed": "蜡棉",
    "leather": "皮革",
    "knitted": "针织",
    "reversible": "双面",
}


def detect_keyword_tags(style_name_en: str) -> list:
    return _detect_keyword_tags(style_name_en, KEYWORD_MAP)


# ==== 随机补齐用安全热词 ====
FILLER_WORDS = [
    "英伦风",
    "百搭",
    "经典款",
    "秋冬",
    "日常",
    "耐用",
    "复古",
    "时尚",
]


def pad_to_60_bytes(base_title: str, style_name_en: str, type_str: str) -> str:
    return _pad_to_60_bytes(
        base_title, style_name_en, type_str,
        KEYWORD_MAP, TYPE_CORE_KEYWORDS, TYPE_EXTRAS, FILLER_WORDS,
    )


# ==== 前缀判定 ====
def detect_by_code_prefix(code: str) -> Tuple[str, str]:
    c = (code or "").upper().strip()
    for pref in sorted(ACCESSORY_PREFIX_RULES.keys(), key=len, reverse=True):
        if c.startswith(pref):
            return ACCESSORY_PREFIX_RULES[pref]  # (gender, type)

    logger.warning(f"[Barbour配件] 未知前缀，请检查是否需要补充 ACCESSORY_PREFIX_RULES: code={c}")
    return "", ""


# ==== 系列提取（白名单 + 黑名单，配件专属词表）====
SERIES_WHITELIST = {
    "tartan",
    "ashby",
    "bristol",
    "border",
}

SERIES_BLACKLIST = {
    # 性别/人群
    "mens",
    "men",
    "women",
    "womens",
    "lady",
    "ladies",
    "kids",
    "kid",
    "boys",
    "girls",
    "child",
    "children",
    # 常见副标题/集合词
    "international",
    "heritage",
    "original",
    "classic",
    "essential",
    "icon",
    "icons",
    "collection",
    "range",
    "limited",
    "edition",
    "new",
    "seasonal",
    "core",
}

NOISE = {
    "barbour",
    "bag",
    "hat",
    "cap",
    "beanie",
    "scarf",
    "belt",
    "hood",
    "wrap",
    "stole",
    "tote",
    "holdall",
    "backpack",
    "duffel",
}


def detect_series(style_name_en: str) -> str:
    return _detect_series(style_name_en, SERIES_WHITELIST, SERIES_BLACKLIST, NOISE)


# ==== 核心：生成淘宝标题 ====
def generate_barbour_accessory_title(code: str, style_name_en: str, color_en: str, brand_key="barbour") -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}"

    gender_str, type_str = detect_by_code_prefix(code)

    series = detect_series(style_name_en)
    if not series:
        # 白名单未命中系列名时，用 DeepSeek 翻译英文款式名作为兜底（失败时 safe_translate 自动回退原文）
        series = sanitize_text(safe_translate(style_name_en, target_lang="ZH")) or style_name_en

    color_cn = map_color(color_en)
    material_cn = detect_material_cn(style_name_en)

    # 1) 初次拼接
    base_title = f"{brand_full}{gender_str}{series}{type_str}{color_cn}{material_cn}".strip()
    base_title = base_title.replace("No Data", "")

    # 2) >60：先去 material（保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series}{type_str}{color_cn}".strip()

    # 3) 仍 >60：再去 color（仍保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series}{type_str}".strip()

    # 4) <60：补齐（关键词优先 → 类型卖点 → 通用词）
    if get_byte_length(base_title) < 60:
        base_title = pad_to_60_bytes(base_title, style_name_en, type_str)

    return {
        "Product Code": code,
        "Title": base_title,
        "Length(bytes,GBK)": get_byte_length(base_title),
    }


if __name__ == "__main__":
    print(generate_barbour_accessory_title("UBA0001BK11", "Tartan Lambswool Holdall Bag", "Black"))
