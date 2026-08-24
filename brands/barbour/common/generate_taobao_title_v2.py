# -*- coding: utf-8 -*-
import re
import random
import unicodedata
from typing import Tuple

from config import BRAND_CONFIG, BRAND_NAME_MAP, BARBOUR
from common.text.translate import safe_translate
from common.text.ad_sanitizer import sanitize_text
from common.utils.logger_utils import setup_logger

logger = setup_logger("barbour_taobao_title")

# ==== 读取前缀规则（性别+类型） ====
_cfg = BRAND_CONFIG.get("barbour") or BRAND_CONFIG.get("Barbour") or {}
CODE_PREFIX_RULES = _cfg.get("CODE_PREFIX_RULES", {})


# ==== 工具 ====
def get_byte_length(text: str) -> int:
    return len((text or "").encode("gbk", errors="ignore"))


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).strip()


# ==== 颜色映射（可扩充）====
COLOR_MAP = BARBOUR["BARBOUR_COLOR_MAP"]


def map_color(color_en: str) -> str:
    c = nfkc(color_en)
    c = re.sub(r"^[\-\:\|•\.\s]+", "", c)  # 去掉开头 "- "
    c = c.split("/")[0].strip()  # 复合色取第一色
    cl = c.lower()
    if cl in COLOR_MAP:
        return COLOR_MAP[cl]
    cl2 = re.sub(r"^(classic|washed|burnt|dark|light)\s+", "", cl).strip()
    return COLOR_MAP.get(cl2, c)


# ==== 材质提示（可扩充）====
MATERIAL_HINTS = [
    (r"\bwax(ed)?\b", "蜡棉"),
    (r"\bquilt(ed|ing)?\b", "绗缝"),
    (r"\bfleece\b", "抓绒"),
    (r"\blinen\b", "亚麻"),
    (r"\bcotton\b", "棉质"),
    (r"\bpolyester\b", "聚酯"),
    (r"\bnylon\b", "尼龙"),
    (r"\bwool\b", "羊毛"),
]


def detect_material_cn(style_name_en: str) -> str:
    s = (style_name_en or "").lower()
    for pat, zh in MATERIAL_HINTS:
        if re.search(pat, s, flags=re.I):
            return zh
    return ""


# ==== 卖点按类型（可选）====
# V2.1：蜡棉夹克 -> 油蜡夹克（国内客户习惯）
TYPE_EXTRAS = {
    "油蜡夹克": ["英伦风", "通勤", "百搭", "春秋冬"],
    "绗缝夹克": ["轻暖", "百搭", "春秋"],
    "休闲夹克": ["百搭", "春秋", "舒适版型", "日常通勤"],
    "派克大衣": ["保暖", "通勤", "秋冬"],
    "内胆": ["保暖", "轻便", "易搭配"],
    "抓绒夹克": ["保暖", "春秋", "舒适", "通勤"],
    "防风防小雨外套": ["通勤", "日常出行", "轻量"],
    "防水夹克": ["防水", "户外", "通勤"],
    "防泼水夹克": ["防泼水", "轻量", "通勤"],
    "马甲": ["叠穿", "轻便", "通勤"],
    "夹克": ["通勤", "百搭", "春秋"],
    "外套": ["通勤", "春秋", "百搭"],
    "卫衣": ["百搭", "休闲", "日常"],
    "风衣": ["英伦风", "通勤", "百搭"],
    "中长连衣裙": ["优雅", "通勤", "百搭", "春夏"],
    "中长裙": ["优雅", "通勤", "百搭", "春夏"],
    "翻领T恤POLO衫": ["短袖", "商务休闲", "苏格兰格纹", "Tartan", "有领"],
    "加厚衬衫外套夹克": ["长袖", "商务休闲","翻领", "百搭"],
    "翻领薄衬衫": ["商务休闲","英伦风", "修身", "透气"],
    "T恤": ["百搭", "休闲", "日常"],
}


# ==== 核心品类关键词（比卖点词更重要，客户高频搜索的大类目词）====
# 同一件商品，不同客户可能搜不同的近义品类词（夹克/外套、马甲/内胆），
# 补上近义词能多接住一批搜索流量。只在真正近似的品类间关联，避免风马牛不相及
# （比如衬衫/T恤/裙装不属于外套，卫衣也不等同于马甲/内胆，不关联）
TYPE_CORE_KEYWORDS = {
    "油蜡夹克": ["外套"],
    "绗缝夹克": ["外套"],
    "休闲夹克": ["外套"],
    "抓绒夹克": ["外套"],
    "防水夹克": ["外套"],
    "防泼水夹克": ["外套"],
    "派克大衣": ["外套"],
    "风衣": ["外套"],
    "夹克": ["外套"],
    "马甲": ["内胆"],
    "内胆": ["马甲"],
}


# ==== 前缀内部混品类时，用英文名关键词做二次判断 ====
# 仅对已确认前缀内部混品类的两组前缀生效，不全局匹配——
# "trench"/"gilet" 等词也会出现在其他前缀商品名的配色/系列名里
# （如 MOS "Overshirt - Trench"、MML "Polo Shirt - Trench"、LKN "Merino Knit - Light Trench"），
# 全局匹配会把这些商品误判成风衣/马甲
_FLEECE_MIXED_PREFIXES = ("MFL", "LFL")       # 同前缀下既有 Fleece Gilet 也有 Fleece Jacket
_SHOWERPROOF_MIXED_PREFIXES = ("MSP", "LSP")  # 同前缀下主要是 Showerproof Jacket，少量是 Trench Coat


def refine_type_by_keywords(code: str, type_str: str, style_name_en: str) -> str:
    c = (code or "").upper().strip()
    text = (style_name_en or "").lower()
    if c.startswith(_FLEECE_MIXED_PREFIXES) and re.search(r"\b(gilet|waistcoat|bodywarmer)\b", text):
        return "马甲"
    if c.startswith(_SHOWERPROOF_MIXED_PREFIXES) and re.search(r"\btrench\b", text):
        return "风衣"
    return type_str


# ==== 重要关键词映射（优先用于补齐 60 字节）====
# 可读性更强：后续直接在这里加词即可
KEYWORD_MAP = {
    "overshirt": "宽松版Overshirt",
    "international": "国际版",
    "waterproof": "防水",
    "lightweight": "轻蜡",
    # Mac 系列：mac / mackintosh / maccoat 都映射为“风衣”
    "mac": "风衣",
    "mackintosh": "风衣",
    "maccoat": "风衣",
    "essential": "基础版",
    "essentials": "基础版",
}


def detect_keyword_tags(style_name_en: str) -> list:
    """
    根据英文名称匹配关键词映射，返回中文标签列表（按 KEYWORD_MAP 的插入顺序，去重）
    """
    text = (style_name_en or "").lower()
    tags = []
    for kw, zh in KEYWORD_MAP.items():
        if kw in text and zh not in tags:
            tags.append(zh)
    return tags


# ==== 随机补齐用安全热词（关键词/类型卖点不够时再用）====
FILLER_WORDS = [
    "英伦风",
    "通勤",
    "百搭",
    "经典款",
    "秋冬",
    "春秋",
    "舒适版型",
    "日常",
    "耐穿",
    "轻便",
    "复古",
    "时尚",
]


def pad_to_60_bytes(base_title: str, style_name_en: str, type_str: str) -> str:
    """
    V2.1：补齐到 60 字节优先级：
    1) KEYWORD_MAP 标签（国际版/防水/轻蜡…）
    2) TYPE_CORE_KEYWORDS 核心品类词（外套…）
    3) TYPE_EXTRAS 类型卖点（通勤/百搭/春秋…）
    4) FILLER_WORDS 通用安全词
    """
    cur = base_title or ""
    if get_byte_length(cur) >= 60:
        return cur

    available = 60 - get_byte_length(cur)

    # 1) 优先补：关键词映射
    for tag in detect_keyword_tags(style_name_en):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    # 2) 再补：核心品类词（如"外套"），优先级高于卖点词
    for tag in TYPE_CORE_KEYWORDS.get(type_str, []):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    # 3) 再补：类型卖点
    for tag in TYPE_EXTRAS.get(type_str, []):
        if available <= 0:
            return cur
        if tag in cur:
            continue
        tlen = get_byte_length(tag)
        if tlen <= available:
            cur += tag
            available -= tlen

    # 4) 最后补：通用安全词
    if available > 0:
        words = FILLER_WORDS[:]
        random.shuffle(words)
        for w in words:
            if available <= 0:
                break
            if w in cur:
                continue
            wlen = get_byte_length(w)
            if wlen <= available:
                cur += w
                available -= wlen

    return cur


# ==== 前缀判定 ====
def detect_by_code_prefix(code: str) -> Tuple[str, str]:
    c = (code or "").upper().strip()
    for pref in sorted(CODE_PREFIX_RULES.keys(), key=len, reverse=True):
        if c.startswith(pref):
            return CODE_PREFIX_RULES[pref]  # (gender, type)

    # 兜底：CODE_PREFIX_RULES 里没有的新前缀，仅按性别猜品类为"夹克"，
    # 并记录警告——避免像 LGI/LFL 那样长期被静默错标而未被发现
    if c and c[0] in ("M", "L"):
        logger.warning(f"[Barbour] 未知前缀，品类兜底为'夹克'，请检查是否需要补充 CODE_PREFIX_RULES: code={c}")
        return ("男款" if c[0] == "M" else "女款", "夹克")
    return "", "夹克"


# ==== 系列提取（白名单 + 黑名单）====
SERIES_WHITELIST = {
    "ashby",
    "bedale",
    "beaufort",
    "liddesdale",
    "annandale",
    "deveron",
    "lowerdale",
    "border",
    "bristol",
    "duke",
    "dukeley",
    "sapper",
    # V2.1：不把 international 当系列词（如要恢复，取消注释）
    # "international",
    "royston",
    "rectifier",
    "sanderling",
    "workers",
    "tracker",
    "tyne",
    "durham",
    "endurance",
    "utility",
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
    "casual",
    "jacket",
    "coat",
    "gilet",
    "vest",
    "liner",
    "parka",
    "harrington",
    "cotton",
    "summer",
    "wash",
    "re-engineered",
    "reengineered",
    "chore",
    "overshirt",
    "polo",
    "shirt",
    "tshirt",
}


def _normalize_token(t: str) -> str:
    """
    把 "Men's" / "Men’s" -> "mens"，并去掉末尾 's。
    """
    if not t:
        return ""
    t = t.strip().lower().replace("’", "'")
    if t.endswith("'s"):
        t = t[:-2]
    return t


def detect_series(style_name_en: str) -> str:
    s = nfkc(style_name_en)
    tokens_raw = re.findall(r"[A-Za-z][A-Za-z'-]+", s)
    tokens = [_normalize_token(t) for t in tokens_raw]

    # 1) 白名单优先（但黑名单覆盖）
    for t_raw, t in zip(tokens_raw, tokens):
        if t in SERIES_BLACKLIST:
            continue
        if t in SERIES_WHITELIST:
            disp = t_raw.replace("’", "'")
            if disp.lower().endswith("'s"):
                disp = disp[:-2]
            return disp.capitalize()

    # 2) 兜底：挑第一个“有意义”的词（排除 NOISE + 黑名单）
    for t_raw, t in zip(tokens_raw, tokens):
        if t in SERIES_BLACKLIST or t in NOISE:
            continue
        if len(t) <= 2:
            continue
        disp = t_raw.replace("’", "'")
        if disp.lower().endswith("'s"):
            disp = disp[:-2]
        return disp.capitalize()

    return ""

def _dedupe_material(type_str: str, material_cn: str) -> str:
    t = type_str or ""
    m = material_cn or ""
    if not m:
        return ""

    # 油蜡夹克（waxed）不再重复“蜡棉”
    if "油蜡" in t and m in ("蜡棉", "油蜡"):
        return ""

    # 绗缝夹克不再重复“绗缝”
    if "绗缝" in t and m in ("绗缝",):
        return ""

    return m

# ==== 核心：生成淘宝标题（V2.1）====
def generate_barbour_taobao_title(code: str, style_name_en: str, color_en: str, brand_key="barbour") -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}"

    gender_str, type_str = detect_by_code_prefix(code)

    # 前缀内部混品类（MFL/LFL、MSP/LSP）时，按英文名关键词二次判断
    type_str = refine_type_by_keywords(code, type_str, style_name_en)

    # V2.1：术语统一（蜡棉夹克 -> 油蜡夹克）
    if type_str == "蜡棉夹克":
        type_str = "油蜡夹克"

    series = detect_series(style_name_en)
    if not series:
        # 白名单未命中系列名时，用 DeepSeek 翻译英文款式名作为兜底（失败时 safe_translate 自动回退原文）
        series = sanitize_text(safe_translate(style_name_en, target_lang="ZH")) or style_name_en

    color_cn = map_color(color_en)
    material_cn = detect_material_cn(style_name_en)

    material_cn = _dedupe_material(type_str, material_cn)

    # 1) 初次拼接：不再提前拼 TYPE_EXTRAS（避免把“通勤百搭春秋”挤到关键词前面）
    base_title = f"{brand_full}{gender_str}{series}{type_str}{color_cn}{material_cn}".strip()
    base_title = base_title.replace("No Data", "")

    # 2) >60：先去 material（保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series}{type_str}{color_cn}".strip()

    # 3) 仍 >60：再去 color（仍保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series}{type_str}".strip()

    # 4) <60：V2.1 补齐（关键词优先 → 类型卖点 → 通用词）
    if get_byte_length(base_title) < 60:
        base_title = pad_to_60_bytes(base_title, style_name_en, type_str)

    return {
        "Product Code": code,
        "Title": base_title,
        "Length(bytes,GBK)": get_byte_length(base_title),
    }
