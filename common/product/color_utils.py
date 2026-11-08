# -*- coding: utf-8 -*-
"""
英文颜色 → 中文颜色。

数据流：TXT 的 Product Color → 导入数据库时用 to_color_cn() 翻译 → 写入库存表 color 字段
       → 发布 Excel / 颜色更新 Excel 都直接读 color 字段。
Product Color 为空时，从英文标题里找颜色词。
中文映射优先用 cfg/taobao_title_keyword_config.py 的 COLOR_MAP / COLOR_GUESS，
再用本文件的 _EXTRA_COLOR_MAP 补充。映射不到时保留英文原文，方便人工补。
多色（如 "Red/Brown"）逐个翻译后用 "/" 连接，重复的只保留一个。
"""
import re

from cfg.taobao_title_keyword_config import COLOR_MAP, COLOR_GUESS

_EXTRA_COLOR_MAP = {
    "yellow": "黄色", "mustard": "芥末黄", "purple": "紫色", "lilac": "淡紫色", "lavender": "薰衣草紫",
    "violet": "紫罗兰色", "moss": "苔绿色", "dark moss": "深苔绿", "sage": "鼠尾草绿", "mint": "薄荷绿",
    "forest": "墨绿色", "emerald": "祖母绿", "teal": "蓝绿色", "turquoise": "绿松石色",
    "ecru": "米色", "oat": "燕麦色", "oatmeal": "燕麦色", "natural": "本色", "nude": "裸色",
    "mocha": "摩卡色", "chocolate": "巧克力色", "coffee": "咖色", "espresso": "深咖色",
    "walnut": "胡桃色", "chestnut": "栗色", "bronze": "古铜色", "copper": "铜色",
    "coral": "珊瑚色", "rose": "玫瑰色", "blush": "浅粉色", "wine": "酒红色", "maroon": "栗红色",
    "garnet": "石榴红", "dark garnet": "深石榴红", "oxblood": "牛血红", "berry": "莓红色",
    "indigo": "靛蓝色", "cobalt": "钴蓝色", "royal blue": "宝蓝色", "midnight": "午夜蓝",
    "ink": "墨蓝色", "slate": "石板灰", "graphite": "石墨灰", "anthracite": "炭黑色",
    "ivory": "象牙白", "snow": "雪白色", "chalk": "粉笔白", "pearl": "珍珠白",
    "trench": "风衣卡其", "tobacco": "烟草棕", "mahogany": "红木色", "caramel": "焦糖色",
    "honey": "蜂蜜色", "biscuit": "饼干色", "fawn": "浅黄褐色", "mushroom": "蘑菇色",
    "leopard": "豹纹", "multi": "多色", "multicolour": "多色", "multicolor": "多色",
    # —— 时装常见色名（Toast / Barbour 等）—— #
    "parchment": "羊皮纸色", "artichoke": "洋蓟绿", "bordeaux": "波尔多红", "seaweed": "海藻绿",
    "amber": "琥珀色", "sepia": "棕褐色", "persimmon": "柿子橙", "ochre": "赭黄色",
    "blueberry": "蓝莓色", "mole": "鼹鼠灰", "earth": "大地色", "iron": "铁灰色",
    "redcurrant": "红醋栗色", "peat": "泥炭棕", "bracken": "蕨棕色", "ginger": "姜黄色",
    "pear": "梨绿色", "brass": "黄铜色", "putty": "油灰色", "rosewood": "玫瑰木色",
    "brick": "砖红色", "steel": "钢灰色", "acorn": "橡果棕", "straw": "稻草黄",
    "wisteria": "紫藤色", "pebble": "卵石灰", "terracotta": "赤陶色", "dune": "沙丘色",
    "whiskey": "威士忌色", "whisky": "威士忌色", "pistachio": "开心果绿", "fern": "蕨绿色",
    "tomato": "番茄红", "spearmint": "薄荷绿", "aubergine": "茄紫色", "tartan": "格纹",
    "mist": "雾灰色", "beech": "山毛榉棕", "concrete": "水泥灰", "rustic": "复古棕",
    "cloud": "云白色", "truffle": "松露棕", "fig": "无花果紫", "neutral": "中性色",
    "nutmeg": "肉豆蔻棕", "asphalt": "沥青灰", "birch": "桦木色", "birchwood": "桦木色",
    "greystone": "灰石色", "sandstone": "砂岩色", "russet": "赤褐色", "oak": "橡木色",
    "thyme": "百里香绿", "ruby": "红宝石色", "henna": "赭红色", "clay": "陶土色",
    "fossil": "化石灰", "moonbeam": "月光白", "mink": "貂灰色", "rust": "铁锈红",
    "smoke": "烟灰色", "ash": "烟灰色", "oyster": "牡蛎白", "bone": "骨白色",
    "mulberry": "桑葚紫", "damson": "李子紫", "heather": "石楠紫", "pine": "松绿色",
    "racing green": "赛车绿", "bottle green": "墨绿色", "petrol": "石油蓝",
    "mauve": "淡紫色", "azure": "天蓝色", "sky": "天蓝色", "chambray": "青年布蓝",
    "cinnamon": "肉桂色", "apple": "苹果绿", "coal": "煤黑色", "granite": "花岗岩灰",
    "sienna": "赭色", "merlot": "梅洛红", "cranberry": "蔓越莓红", "evergreen": "常青绿",
    "bark": "树皮棕", "cement": "水泥灰", "umber": "赭褐色", "fog": "雾灰色", "teak": "柚木色",
    "eggshell": "蛋壳白", "apricot": "杏色", "aluminium": "铝灰色", "loden": "洛登绿",
    "pecan": "碧根果棕", "spice": "香料棕", "peacock": "孔雀蓝", "lime": "青柠绿",
    "safari": "狩猎卡其", "jasmine": "茉莉白", "brindle": "斑纹棕", "coriander": "芫荽绿",
    "wildberry": "野莓红", "raspberry": "覆盆子红", "cumin": "孜然棕", "sapphire": "宝石蓝",
    "thistle": "蓟紫色", "butternut": "南瓜黄", "port": "波特酒红", "linen": "亚麻色",
    "pepper": "胡椒灰", "peppercorn": "胡椒灰", "citron": "香橼黄", "soil": "泥土棕",
}

# Dark / Light 前缀 → 深 / 浅（仅对 "xx色" 形式的基础色加前缀）
_SHADE_PREFIX = {"dark": "深", "deep": "深", "light": "浅", "pale": "浅"}

# 合并词表：cfg 的映射优先
_ALL_COLORS: dict[str, str] = {**_EXTRA_COLOR_MAP, **COLOR_GUESS, **COLOR_MAP}
# 长词优先匹配（"dark brown" 先于 "brown"）
_KEYS_BY_LEN = sorted(_ALL_COLORS, key=len, reverse=True)

_EMPTY_VALUES = {"", "no data", "n/a", "na", "none", "null", "-"}


def _norm(s: str) -> str:
    s = (s or "").strip().lower().replace("_", " ").replace("-", " ")
    s = s.replace("colour", "color")
    return re.sub(r"\s+", " ", s).strip()


def _find_colors(text: str, first_only: bool = False) -> list[str]:
    """在一段英文里按词边界找颜色词，返回中文列表（去重保序）"""
    t = f" {_norm(text)} "
    hits: list[tuple[int, str]] = []
    covered: list[tuple[int, int]] = []
    for k in _KEYS_BY_LEN:
        for m in re.finditer(rf"(?<![a-z]){re.escape(_norm(k))}(?![a-z])", t):
            # 跳过已被更长词覆盖的位置（"dark brown" 里的 "brown"）
            if any(s <= m.start() < e for s, e in covered):
                continue
            covered.append((m.start(), m.end()))
            hits.append((m.start(), k))
    hits.sort()
    out = list(dict.fromkeys(_ALL_COLORS[k] for _, k in hits))
    return out[:1] if first_only else out


def _clean_color_en(raw: str) -> str:
    """去掉前导 '- ' 等符号；'No Data' 等视为空"""
    val = re.sub(r"^[\-\:\|•\.\s]+", "", (raw or "").strip()).strip()
    return "" if val.lower() in _EMPTY_VALUES else val


def to_color_cn(color_en: str, title_en: str = "") -> str:
    """
    TXT 的 Product Color 原值 → 中文颜色。
    Product Color 为空时，从英文标题里找颜色词；都没有返回 ""。
    """
    color_en = _clean_color_en(color_en)
    if color_en:
        return _color_en_to_cn(color_en)
    found = _find_colors(title_en, first_only=True)
    return found[0] if found else ""


def _color_en_to_cn(color_en: str) -> str:
    """多色用 '/' 连接；完全映射不到时返回英文原文"""
    parts = [p for p in re.split(r"\s*(?:/|&|,|\+|\band\b)\s*", color_en) if p.strip()]
    mapped: list[str] = []
    for p in parts:
        cn = _part_to_cn(p)
        if cn:
            mapped.append(cn)
    if not mapped:
        return color_en.strip()          # 完全映射不到 → 保留英文，人工补
    return "/".join(dict.fromkeys(mapped))  # 部分映射不到的直接丢弃


def _part_to_cn(part: str) -> str:
    key = _norm(part)
    if key in _ALL_COLORS:
        return _ALL_COLORS[key]
    found = _find_colors(part, first_only=True)
    if not found:
        return ""
    cn = found[0]
    first = key.split(" ", 1)[0]
    if first in _SHADE_PREFIX and cn.endswith("色") and cn[0] not in "深浅":
        cn = _SHADE_PREFIX[first] + cn
    return cn
