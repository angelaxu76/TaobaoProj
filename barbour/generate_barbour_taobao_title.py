# -*- coding: utf-8 -*-
import re, random, unicodedata
from typing import Tuple
from config import BRAND_CONFIG, BRAND_NAME_MAP

# ==== 读取前缀规则（性别+类型） ====
_cfg = BRAND_CONFIG.get("barbour") or BRAND_CONFIG.get("Barbour") or {}
CODE_PREFIX_RULES = _cfg.get("CODE_PREFIX_RULES", {})

# ==== 工具 ====
def get_byte_length(text: str) -> int:
    return len(text.encode("gbk", errors="ignore"))

def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).strip()

# ==== 颜色映射（可扩充）====
COLOR_MAP = {
    "classic navy": "海军蓝",
    "black": "黑色",
    "olive": "橄榄绿",
    "sage": "鼠尾草绿",
    "sandstone": "砂岩色",
    "bark": "树皮棕",
    "rustic": "乡村棕",
    "stone": "石色",
    "charcoal": "炭灰",
    "navy": "深蓝",
    "blue": "蓝色",
    "light moss": "浅苔绿",
    "brown": "棕色",
    "dark brown": "深棕",
    "rust": "铁锈红",
    "red": "红色",
    "burgundy": "酒红",
    "yellow": "黄色",
    "mustard": "芥末黄",
    "khaki": "卡其色",
    "forest": "森林绿",
    "dusky green": "暗绿色",
    "uniform green": "军绿色",
    "emerald": "祖母绿",
    "antique pine": "古松木色",
    "pale pink": "浅粉",
    "pink": "粉色",
    "rose": "玫瑰粉",
    "cream": "奶油色",
    "off white": "米白",
    "white": "白色",
    "grey": "灰色",
    "mineral grey": "矿物灰",
    "washed cobalt": "钴蓝色",
    "timberwolf": "灰棕色",
    "burnt heather": "焦石楠色",
    "mist": "雾灰色",
    "concrete": "混凝土灰",
    "dark denim": "深牛仔蓝",
    "empire green": "帝国绿",
    "royal blue": "宝蓝",
    "classic tartan": "经典格纹",
    "tartan": "格纹",
    "beige": "米色",
    "tan": "茶色",
    "walnut": "胡桃棕",
    "plum": "李子紫",
    "orange": "橙色",
    "bronze": "青铜色",
    "silver": "银色",
    "pewter": "锡灰",
    "cola": "可乐棕",
    "taupe": "灰褐色",
}


def map_color(color_en: str) -> str:
    c = nfkc(color_en)
    c = re.sub(r"^[\-\:\|•\.\s]+", "", c)  # 去掉开头 "- "
    c = c.split("/")[0].strip()            # 复合色取第一色
    cl = c.lower()
    if cl in COLOR_MAP: return COLOR_MAP[cl]
    cl2 = re.sub(r"^(classic|washed|burnt|dark|light)\s+", "", cl)
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
TYPE_EXTRAS = {
    "蜡棉夹克":       ["英伦风","通勤","春秋冬"],
    "绗缝夹克":       ["轻暖","百搭","春秋"],
    "休闲夹克":       ["百搭","春秋","舒适版型","日常通勤"],
    "派克大衣":       ["保暖","通勤","秋冬"],
    "内胆":           ["保暖","轻便","易搭配"],
    "抓绒夹克":       ["保暖","春秋","舒适","通勤"],
    "防风防小雨外套": ["通勤","日常出行","轻量"],
    "马甲":           ["叠穿","轻便","通勤"],
    "夹克":           ["通勤","百搭","春秋"],
    "外套":           ["通勤","春秋","百搭"],
}

# ==== 随机补齐用安全热词 ====
FILLER_WORDS = [
    "英伦风","通勤","百搭","经典款","秋冬","春秋","舒适版型","日常","耐穿","轻便","复古","时尚"
]

# ==== 前缀判定 ====
def detect_by_code_prefix(code: str) -> Tuple[str, str]:
    c = (code or "").upper().strip()
    for pref in sorted(CODE_PREFIX_RULES.keys(), key=len, reverse=True):
        if c.startswith(pref):
            return CODE_PREFIX_RULES[pref]  # (gender, type)
    # 兜底：仅性别
    if c and c[0] in ("M","L"):
        return ("男款" if c[0]=="M" else "女款", "夹克")
    return "","夹克"

# ==== 系列提取（可沿用你之前的更完整版本）====
SERIES_WHITELIST = {
    "ashby","bedale","beaufort","liddesdale","annandale","deveron","lowerdale",
    "border","bristol","duke","dukeley","sapper","international",
    "royston","rectifier","sanderling","workers","tracker","tyne","durham","endurance","utility"
}
NOISE = {"barbour","casual","jacket","coat","gilet","vest","liner","parka",
         "harrington","cotton","summer","wash","re-engineered","reengineered","chore","overshirt"}

def detect_series(style_name_en: str) -> str:
    s = nfkc(style_name_en)
    tokens = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z'-]+", s)]
    for t in tokens:
        if t in SERIES_WHITELIST:
            return t.capitalize()
    for t in tokens:
        if t not in NOISE:
            return t.capitalize()
    return ""

# ==== 核心：严格按你给的拼接与补齐逻辑 ====
def generate_barbour_taobao_title(code: str, style_name_en: str, color_en: str, brand_key="barbour") -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    gender_str, type_str = detect_by_code_prefix(code)
    series = detect_series(style_name_en)
    color_cn = map_color(color_en)
    material_cn = detect_material_cn(style_name_en)

    # 卖点（可按需要自定义；这里用类型对应的 extras 组合）
    extras = TYPE_EXTRAS.get(type_str, [])
    features_str = "".join(extras)  # 注意：这里拼接为连写，如果你想空格分隔，可改为 " ".join(extras)

    # 1) 初次拼接
    base_title = f"{brand_full}{gender_str}{series or style_name_en}{type_str}{color_cn}{material_cn}{features_str}".strip()
    base_title = base_title.replace("No Data", "")

    # 2) >60：先去 features（保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series or style_name_en}{type_str}{color_cn}{material_cn}".strip()

    # 3) 仍 >60：去 material（仍保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series or style_name_en}{type_str}{color_cn}".strip()

    # 4) 仍 >60：再去 color（仍保留 type）
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{series or style_name_en}{type_str}".strip()

    # 5) <60：按你原逻辑补词直到 60
    if get_byte_length(base_title) < 60:
        available_bytes = 60 - get_byte_length(base_title)
        random.shuffle(FILLER_WORDS)
        for word in FILLER_WORDS:
            wlen = get_byte_length(word)
            if wlen <= available_bytes:
                base_title += word
                available_bytes -= wlen
            else:
                break

    return {
        "Product Code": code,
        "Title": base_title,
        "Length(bytes,GBK)": get_byte_length(base_title)
    }
