# -*- coding: utf-8 -*-
"""
生成 Barbour 配件类（包/帽子/围巾/皮带/礼盒/宠物用品等）淘宝标题。

与 generate_taobao_title_v2.py（服装/夹克类）分开维护：服装按"前缀→一个品类"
命名，配件同一前缀下品类很杂（MAC 既有皮带也有围巾，DAC 有项圈/牵引绳/狗窝），
所以这里按英文商品名逐个识别品类词，一个商品可命中多个品类词。

标题拼接顺序：
    品牌 + 性别 + 款式名 + 品类词(可多个) + 颜色 + 材质(可多个)
超过 60 字节（GBK）时按优先级舍弃次要词（见 _assemble），
不足 60 字节再用卖点词/通用热词补齐（title_shared.pad_to_60_bytes）。

前缀→(性别, 默认品类) 见 cfg/brands/barbour.py ACCESSORY_PREFIX_RULES。
"""
import re
from typing import List, Optional, Tuple

from config import BRAND_CONFIG, BRAND_NAME_MAP
from common.utils.logger_utils import setup_logger
from brands.barbour.common.title_shared import (
    get_byte_length,
    map_color,
    nfkc,
    detect_series as _detect_series,
    pad_to_60_bytes as _pad_to_60_bytes,
)

logger = setup_logger("barbour_taobao_title_accessories")

MAX_BYTES = 60

# ==== 前缀规则（配件品类，见 cfg/brands/barbour.py ACCESSORY_PREFIX_RULES）====
_cfg = BRAND_CONFIG.get("barbour") or BRAND_CONFIG.get("Barbour") or {}
ACCESSORY_PREFIX_RULES = _cfg.get("ACCESSORY_PREFIX_RULES", {})


def is_accessory_code(code: str) -> bool:
    """编码前缀是否属于配件类（发布 Excel 据此选择配件标题生成）。"""
    c = (code or "").upper().strip()
    return any(c.startswith(p) for p in ACCESSORY_PREFIX_RULES)


# ==== 品类词规则 ====
# (正则, [品类词...], 卖点分组)。按顺序匹配英文商品名，不同分组的规则可同时命中
# （如 "Beanie & Scarf Gift Set" → 毛线帽 + 围巾 + 礼盒）：
#   每条规则的第 1 个词是"核心品类词"，其余是"近义品类词"（空间不够时先舍弃）。
# 同一分组只取第一个命中的规则，所以越具体的写在越前面（Flat Cap 不会再命中通用 cap）。
# 第一个命中规则的分组决定补齐用的卖点词。
CATEGORY_RULES: List[Tuple[str, List[str], str]] = [
    # —— 包 ——
    (r"\bcross\s?body\b|\bmessenger\b|\bsling\b", ["斜挎包", "单肩包"], "包"),
    (r"\btote\b", ["托特包", "手提包"], "包"),
    (r"\bshoulder\s+bag\b", ["单肩包"], "包"),
    (r"\bback\s?pack\b|\brucksack\b", ["双肩包", "背包"], "包"),
    (r"\bholdall\b|\bduffe?l\b|\bweekender\b|\btravel\s+bag\b", ["旅行包", "行李包"], "包"),
    (r"\bbucket\s+bag\b", ["水桶包"], "包"),
    (r"\bwash\s?bag\b", ["洗漱包", "收纳包"], "包"),
    (r"\bbriefcase\b", ["公文包"], "包"),
    (r"\bboot\s+bag\b", ["靴袋", "收纳袋"], "包"),
    (r"\bwallet\b|\bpurse\b|\bcard\s+holder\b", ["钱包"], "包"),
    (r"\bbag\b", ["包"], "包"),
    # —— 帽子 ——
    (r"\bbeanie\b", ["毛线帽", "针织帽"], "帽子"),
    (r"\bbucket\s+hat\b", ["渔夫帽"], "帽子"),
    (r"\bflat\s+cap\b", ["平顶帽", "鸭舌帽"], "帽子"),
    (r"\bbaker\s?boy\b", ["报童帽"], "帽子"),
    (r"\btrucker\b|\bbaseball\b|\bsports?\s+cap\b|\bcap\b", ["棒球帽", "鸭舌帽"], "帽子"),
    (r"\btrilby\b|\bfedora\b", ["礼帽", "爵士帽"], "帽子"),
    (r"\btrapper\b", ["雷锋帽", "护耳帽"], "帽子"),
    (r"\bberet\b", ["贝雷帽"], "帽子"),
    (r"\bsafari\b|\bbushman\b|\bsun\s+hat\b", ["遮阳帽", "户外帽"], "帽子"),
    (r"\bhat\b", ["帽子"], "帽子"),
    (r"\bhood\b", ["兜帽", "可拆卸连帽"], "兜帽"),
    # —— 围巾 / 手套 / 袜子 ——
    (r"\bsnood\b", ["围脖"], "围巾"),
    (r"\bbandana\b", ["方巾", "头巾"], "围巾"),
    (r"\bscarf\b|\bwrap\b|\bstole\b|\bserape\b", ["围巾", "披肩"], "围巾"),
    (r"\bgloves?\b", ["手套"], "手套"),
    (r"\bsocks?\b", ["袜子"], "袜子"),
    # —— 其他配饰 ——
    (r"\bbelt\b", ["皮带", "腰带"], "皮带"),
    (r"\bumbrella\b", ["雨伞"], "配饰"),
    (r"\bkey\s?(fob|ring|chain)\b", ["钥匙扣"], "配饰"),
    (r"\btowel\b", ["毛巾"], "配饰"),
    (r"\bstocking\b", ["圣诞袜"], "礼盒"),
    (r"\bbadge\b|\bpin\b", ["徽章", "胸针"], "配饰"),
    (r"\bgaiters?\b", ["绑腿", "护腿"], "鞋类配件"),
    (r"\bcare\s+kit\b|\bdressing\b|\bre-?proofer\b|\bspray\b|\bconditioner\b|\bcleaner\b",
     ["护理用品", "保养"], "护理"),
    # —— 礼盒（通常和上面的帽子/围巾等一起命中）——
    (r"\bgift\b|\bset\b|\bboxed\b", ["礼盒", "送礼"], "礼盒"),
]

# 宠物用品：仅当 DAC 前缀或商品名含 dog 时才匹配（避免 bed/toy/coat 误伤其他商品）
DOG_CATEGORY_RULES: List[Tuple[str, List[str], str]] = [
    (r"\bcollar\b", ["狗项圈"], "宠物用品"),
    (r"\blead\b|\bleash\b", ["狗牵引绳"], "宠物用品"),
    (r"\bharness\b", ["狗胸背带"], "宠物用品"),
    (r"\bbed\b", ["狗窝", "宠物窝"], "宠物用品"),
    (r"\btoy\b", ["狗玩具", "宠物玩具"], "宠物用品"),
    (r"\bblanket\b", ["宠物毯"], "宠物用品"),
    (r"\bcoat\b|\bjacket\b", ["狗衣服"], "宠物用品"),
    (r"\bbowl\b", ["宠物碗"], "宠物用品"),
    (r"\bbow\s+tie\b", ["狗领结"], "宠物用品"),
    (r"\bmat\b", ["宠物垫"], "宠物用品"),
]

# ==== 材质（商品名 + 描述都会匹配，可命中多个）====
# 顺序即优先级；同组互斥的写在 exclude 里（如命中"小羊毛"就不再加"羊毛"）
MATERIAL_RULES: List[Tuple[str, str, Tuple[str, ...]]] = [
    (r"\bfaux\s+leather\b", "仿皮", ()),
    (r"\bfaux\s+fur\b", "仿皮草", ()),
    (r"\bwax(ed)?\b|\bsylkoil\b", "油蜡", ()),
    (r"\bleather\b", "真皮", ("仿皮",)),
    (r"\bsuede\b", "反绒皮", ()),
    (r"\bquilt(ed)?\b", "绗缝", ()),
    (r"\blambswool\b", "小羊毛", ()),
    (r"\bcashmere\b", "羊绒", ()),
    (r"\bwool\b", "羊毛", ("小羊毛",)),
    (r"\btweed\b", "粗花呢", ()),
    (r"\btartan\b", "苏格兰格纹", ()),
    (r"\bcheck\b|\bgingham\b|\btattersall\b|\bplaid\b", "格纹", ("苏格兰格纹",)),
    (r"\bcord(uroy)?\b", "灯芯绒", ()),
    (r"\bdenim\b", "牛仔", ()),
    (r"\bcanvas\b", "帆布", ()),
    (r"\bknit(ted)?\b|\bcable\b|\bcrochet\b|\bfair\s?isle\b", "针织", ()),
    (r"\bboucle\b", "圈圈纱", ()),
    (r"\bfleece\b", "抓绒", ()),
    (r"\bcotton\b", "棉", ("油蜡",)),
    (r"\bnylon\b", "尼龙", ()),
]
# 商品名里识别不到材质时，才从描述里找；且只认这些主面料
# （描述里常有 "cotton lining" / "leather trims" 之类辅料，全用会带偏）
# （真皮也不从描述取：帽子/围巾描述里的 leather 多是皮标）
DESC_MATERIAL_WHITELIST = {"小羊毛", "羊绒", "羊毛", "油蜡", "帆布"}

# ==== 卖点关键词（补齐阶段优先使用）====
KEYWORD_MAP = {
    "reversible": "双面",
    "waterproof": "防水",
    "showerproof": "防泼水",
    "crushable": "可折叠",
    "packable": "可收纳",
    "reflective": "反光",
    "mini": "迷你",
    "large": "大号",
    "pom": "毛球",
    "christmas": "圣诞",
}

# ==== 卖点按品类分组 ====
TYPE_EXTRAS = {
    "包": ["英伦风", "百搭", "通勤", "大容量", "日常出行"],
    "帽子": ["英伦风", "百搭", "保暖", "秋冬", "户外"],
    "兜帽": ["可拆卸", "百搭", "防风", "秋冬"],
    "围巾": ["英伦风", "保暖", "百搭", "秋冬"],
    "手套": ["保暖", "秋冬", "户外"],
    "袜子": ["保暖", "舒适", "秋冬"],
    "皮带": ["英伦风", "百搭", "商务休闲"],
    "礼盒": ["送礼", "节日礼物", "英伦风"],
    "鞋类配件": ["户外", "收纳", "耐用"],
    "护理": ["夹克保养", "户外", "耐用"],
    "宠物用品": ["遛狗", "户外", "耐用", "英伦风"],
    "配饰": ["英伦风", "百搭", "送礼"],
}

FILLER_WORDS = ["英伦风", "百搭", "经典款", "秋冬", "日常", "耐用", "复古", "时尚"]

# ==== 款式名提取（跳过品牌/性别/品类/材质/颜色等泛词，只留 Alder、Monaco 这类款式名）====
SERIES_WHITELIST: set = set()
SERIES_BLACKLIST = {
    "mens", "men", "women", "womens", "woman", "lady", "ladies", "unisex",
    "kids", "kid", "boys", "girls", "child", "children",
    "international", "heritage", "original", "classic", "essential", "icon", "icons",
    "collection", "range", "limited", "edition", "new", "seasonal", "core",
}
NOISE = {
    "barbour", "and", "the", "with", "for", "dog", "gift", "set", "boxed", "box",
    # 品类
    "bag", "bags", "tote", "crossbody", "cross", "body", "messenger", "sling", "shoulder",
    "backpack", "rucksack", "holdall", "duffle", "duffel", "weekender", "travel", "bucket",
    "washbag", "wash", "briefcase", "wallet", "purse", "card", "holder", "boot", "carry", "all",
    "hat", "cap", "beanie", "flat", "bakerboy", "trucker", "baseball", "sports", "sport",
    "trilby", "fedora", "trapper", "beret", "safari", "bushman", "sun", "hood",
    "scarf", "snood", "bandana", "wrap", "stole", "gloves", "glove", "socks", "sock",
    "belt", "umbrella", "key", "fob", "ring", "towel", "stocking", "badge", "pin",
    "gaiters", "care", "kit", "dressing", "spray", "collar", "lead", "harness", "bed",
    "toy", "blanket", "coat", "jacket", "bowl", "bow", "tie", "cage", "mat",
    # 材质 / 工艺 / 图案
    "leather", "faux", "fur", "suede", "wax", "waxed", "quilted", "quilt", "lambswool",
    "wool", "cashmere", "tweed", "tartan", "check", "gingham", "plaid", "cord", "denim",
    "canvas", "knit", "knitted", "cable", "crochet", "fair", "isle", "fairisle", "boucle",
    "fleece", "cotton", "nylon", "printed", "woven", "stripe", "logo", "patchwork",
    "plain", "trimmed", "slip", "rubber", "buffing", "footwear", "serape", "triangular",
    # 尺寸 / 卖点
    "mini", "large", "small", "soft", "reversible", "waterproof", "showerproof",
    "crushable", "packable", "reflective", "lightweight", "pom", "pompom", "christmas",
    # 颜色
    "black", "navy", "olive", "brown", "green", "grey", "gray", "blue", "red", "pink",
    "tan", "sand", "stone", "cream", "white", "dark", "light", "natural", "rose",
    "dusty", "ancient", "dress",
}

# 联名款：命中则作为款式名输出（优先于普通款式名）
COLLAB_MAP = [
    (r"\bpaul\s+smith\b", "Paul Smith联名"),
    (r"\bganni\b", "GANNI联名"),
]


def detect_series(style_name_en: str) -> str:
    s = style_name_en or ""
    for pat, zh in COLLAB_MAP:
        if re.search(pat, s, flags=re.I):
            return zh
    return _detect_series(s, SERIES_WHITELIST, SERIES_BLACKLIST, NOISE)


def detect_gender(code: str, style_name_en: str) -> str:
    s = (style_name_en or "").lower()
    if re.search(r"\bunisex\b", s):
        return "男女同款"
    if re.search(r"\b(womens?|women's|ladies|lady)\b", s):
        return "女士"
    if re.search(r"\b(mens?|men's)\b", s):
        return "男士"
    return detect_by_code_prefix(code)[0]


def detect_by_code_prefix(code: str) -> Tuple[str, str]:
    c = (code or "").upper().strip()
    for pref in sorted(ACCESSORY_PREFIX_RULES.keys(), key=len, reverse=True):
        if c.startswith(pref):
            return ACCESSORY_PREFIX_RULES[pref]  # (gender, default_type)

    logger.warning(f"[Barbour配件] 未知前缀，请检查是否需要补充 ACCESSORY_PREFIX_RULES: code={c}")
    return "", ""


def detect_categories(code: str, style_name_en: str) -> Tuple[List[str], List[str], str]:
    """
    返回 (核心品类词列表, 近义品类词列表, 卖点分组)。
    识别不到任何品类词时，用前缀默认品类兜底。
    """
    s = nfkc(style_name_en).lower()
    is_dog = (code or "").upper().startswith("DAC") or re.search(r"\bdog\b|\bslip\s+lead\b", s)
    rules = (DOG_CATEGORY_RULES if is_dog else []) + CATEGORY_RULES

    core, extra, group = [], [], ""
    matched_groups = set()
    for pat, words, grp in rules:
        if grp in matched_groups or not re.search(pat, s):
            continue
        matched_groups.add(grp)
        if not group:
            group = grp
        head, *rest = words
        if head not in core:
            core.append(head)
        extra.extend(w for w in rest if w not in extra)

    if not core:
        default_type = detect_by_code_prefix(code)[1]
        if default_type:
            core = [default_type]
            group = default_type
    extra = [w for w in extra if w not in core]
    return core, extra, group or "配饰"


def detect_materials(style_name_en: str, description: Optional[str] = None) -> List[str]:
    def _scan(text: str, allowed=None) -> List[str]:
        found: List[str] = []
        for pat, zh, excludes in MATERIAL_RULES:
            if allowed is not None and zh not in allowed:
                continue
            if zh in found or any(e in found for e in excludes):
                continue
            if re.search(pat, text):
                found.append(zh)
        return found

    return (_scan((style_name_en or "").lower())
            or _scan((description or "").lower(), DESC_MATERIAL_WHITELIST))


def _assemble(brand: str, gender: str, series: str, core: List[str], extra: List[str],
              color_cn: str, materials: List[str]) -> str:
    """
    在 60 字节内挑选词语，再按固定顺序拼接：
        品牌 性别 款式名 核心品类词 近义品类词 颜色 材质
    挑选优先级（放不下就跳过该词）：
        品牌、第 1 个核心品类词 > 性别 > 款式名 > 颜色 > 其余核心品类词
        > 第 1 个材质 > 近义品类词 > 其余材质
    """
    chosen = set()
    budget = MAX_BYTES

    def take(key, word):
        nonlocal budget
        if not word:
            return
        n = get_byte_length(word)
        if n <= budget:
            chosen.add(key)
            budget -= n

    take(("brand", 0), brand)
    if core:
        take(("core", 0), core[0])
    take(("gender", 0), gender)
    take(("series", 0), series)
    take(("color", 0), color_cn)
    for i, w in enumerate(core[1:], start=1):
        take(("core", i), w)
    if materials:
        take(("mat", 0), materials[0])
    for i, w in enumerate(extra):
        take(("extra", i), w)
    for i, w in enumerate(materials[1:], start=1):
        take(("mat", i), w)

    parts = [brand if ("brand", 0) in chosen else "",
             gender if ("gender", 0) in chosen else "",
             series if ("series", 0) in chosen else ""]
    parts += [w for i, w in enumerate(core) if ("core", i) in chosen]
    parts += [w for i, w in enumerate(extra) if ("extra", i) in chosen]
    parts.append(color_cn if ("color", 0) in chosen else "")
    parts += [w for i, w in enumerate(materials) if ("mat", i) in chosen]
    return "".join(p for p in parts if p)


# ==== 核心：生成淘宝标题 ====
def generate_barbour_accessory_title(code: str, style_name_en: str, color_en: str,
                                     brand_key="barbour", description: Optional[str] = None) -> dict:
    brand_en, _brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))

    gender = detect_gender(code, style_name_en)
    series = detect_series(style_name_en)
    core, extra, group = detect_categories(code, style_name_en)
    materials = detect_materials(style_name_en, description)

    # 色卡里没有的颜色（返回的仍是英文，如 "Silver Birch"）不放进标题
    color_cn = map_color(color_en or "")
    if re.search(r"[A-Za-z]", color_cn or ""):
        color_cn = ""
    # 颜色与材质/图案重复时（如 "经典格纹" vs "苏格兰格纹"）只保留材质
    if color_cn and any(color_cn[-2:] in m or m in color_cn for m in materials):
        color_cn = ""

    title = _assemble(brand_en, gender, series, core, extra, color_cn, materials)

    if get_byte_length(title) < MAX_BYTES:
        title = _pad_to_60_bytes(title, style_name_en, group,
                                 KEYWORD_MAP, {}, TYPE_EXTRAS, FILLER_WORDS)

    return {
        "Product Code": code,
        "Title": title,
        "Length(bytes,GBK)": get_byte_length(title),
    }


if __name__ == "__main__":
    for args in [
        ("UBA0003OL71", "Waxed Leather Tarras Bag", "Olive"),
        ("LBA0487BK11", "Barbour Alder Leather Tote Bag", "Black"),
        ("LGS0023BK11", "Barbour Saltburn Beanie & Scarf Set", "Black"),
        ("DAC0009TN11", "Barbour Tartan Dog Lead", "Classic Tartan"),
        ("MHA0001BK91", "Barbour Mens Wax Sports Hat", "Black"),
    ]:
        print(generate_barbour_accessory_title(*args))
