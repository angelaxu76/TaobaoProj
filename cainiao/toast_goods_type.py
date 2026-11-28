# -*- coding: utf-8 -*-
"""
TOAST 菜鸟货品：toast_inventory.style_category（+ 英文名 product_title 细分）→ 中文货品名称 + 包装尺寸重量。

  货品名称格式：TOAST{女装/男装/女士/男士/男女同款}{品类}{编码}尺码{size}
    例：TOAST女装长裤WTRWW24INDI尺码8、TOAST女士项链6SWAISILV尺码One Size

  style_category 为空时，用英文名按 CATEGORY_MAP 的英文 key 再匹配一次，仍识别不到兜底 "服装"。
"""
import re
from typing import Dict, Tuple

BRAND_LABEL = "TOAST"

TYPE_CLOTHING = "服装"

# style_category → (大类, 中文品类)。大类决定性别写法（服装：女装/男装；其他：女士/男士）和包装规格
CATEGORY_MAP: Dict[str, Tuple[str, str]] = {
    # 下装
    "trousers": (TYPE_CLOTHING, "长裤"),
    "jeans": (TYPE_CLOTHING, "牛仔裤"),
    "shorts": (TYPE_CLOTHING, "短裤"),
    "culottes": (TYPE_CLOTHING, "阔腿裤"),
    "skirts": (TYPE_CLOTHING, "半身裙"),
    # 上装
    "shirts": (TYPE_CLOTHING, "衬衫"),
    "tees": (TYPE_CLOTHING, "T恤"),
    "tops": (TYPE_CLOTHING, "上衣"),
    "tanks": (TYPE_CLOTHING, "背心"),
    "sweaters": (TYPE_CLOTHING, "毛衣"),
    "cardigans": (TYPE_CLOTHING, "开衫"),
    # 外套
    "jackets": (TYPE_CLOTHING, "夹克"),
    "coats": (TYPE_CLOTHING, "大衣"),
    "ponchos": (TYPE_CLOTHING, "斗篷"),
    # 连体 / 裙装 / 家居
    "dresses": (TYPE_CLOTHING, "连衣裙"),
    "jumpsuits": (TYPE_CLOTHING, "连体裤"),
    "pyjamas": (TYPE_CLOTHING, "睡衣"),
    "nightdresses": (TYPE_CLOTHING, "睡裙"),
    "gowns": (TYPE_CLOTHING, "睡袍"),
    # 配件
    "socks": ("袜子", "袜子"),
    "tights": ("袜子", "连裤袜"),
    "scarves": ("围巾", "围巾"),
    "hats": ("帽子", "帽子"),
    "gloves": ("手套", "手套"),
    "bags": ("包", "包"),
    "belts": ("皮带", "腰带"),
    "jewellery": ("首饰", "首饰"),
}

# 按英文名细分（大类相同才替换品类，如 Jewellery 里区分项链/耳环/戒指）
TITLE_REFINE = [
    (r"\bnecklace\b|\bpendant\b", "首饰", "项链"),
    (r"\bearrings?\b", "首饰", "耳环"),
    (r"\brings?\b", "首饰", "戒指"),
    (r"\bbangle\b|\bbracelet\b|\bcuff\b", "首饰", "手镯"),
    (r"\bbrooch\b", "首饰", "胸针"),
    (r"\bwallet\b|\bpurse\b|\bcard\s+holder\b", "包", "钱包"),
    (r"\bwash\s?bag\b", "包", "洗漱包"),
    (r"\blaptop\b", "包", "电脑包"),
    (r"\bcross\s?body\b", "包", "斜挎包"),
    (r"\btote\b", "包", "托特包"),
    (r"\bback\s?pack\b|\brucksack\b", "包", "双肩包"),
    (r"\bbeanie\b", "帽子", "毛线帽"),
    (r"\bbucket\s+hat\b", "帽子", "渔夫帽"),
    (r"\bcap\b", "帽子", "棒球帽"),
    (r"\bhood\b", "帽子", "兜帽"),
    (r"\bbandana\b", "围巾", "方巾"),
    (r"\bmittens?\b", "手套", "连指手套"),
    (r"\bsnood\b", "围巾", "围脖"),
    (r"\bwaistcoat\b|\bgilet\b|\bvest\b", TYPE_CLOTHING, "马甲"),
    (r"\b(?:dungaree|pinafore)\s+dress\b", TYPE_CLOTHING, "背带裙"),
    (r"\boveralls?\b|\bdungarees?\b", TYPE_CLOTHING, "背带裤"),
]

# 包装尺寸/重量（长宽高 mm，重量 g）。未配置的大类走 _DEFAULT_PACKAGE（与其他品牌默认值一致）
# 帽子沿用 Barbour 的帽子规格；其他配件（袜子/围巾/首饰…）实际尺寸重量确认后在这里补
_DEFAULT_PACKAGE = {"长": 400, "宽": 300, "高": 70, "毛重": 1200, "净重": 900}
PACKAGE_SPEC_BY_TYPE: Dict[str, Dict[str, int]] = {
    TYPE_CLOTHING: _DEFAULT_PACKAGE,
    "帽子": {"长": 300, "宽": 250, "高": 120, "毛重": 400, "净重": 200},
}


def _gender_label(goods_type: str, gender: str) -> str:
    g = (gender or "").strip().lower()
    if goods_type == TYPE_CLOTHING:
        return {"women": "女装", "men": "男装"}.get(g, "")
    return {"women": "女士", "men": "男士", "unisex": "男女同款"}.get(g, "")


def classify_toast_goods(style_category: str = "", title: str = "", gender: str = "") -> Tuple[str, str, str]:
    """返回 (goods_type, gender_label, style_zh)"""
    cat = (style_category or "").strip().lower()
    t = (title or "").lower()
    goods_type, style_zh = CATEGORY_MAP.get(cat, ("", ""))
    if not goods_type:
        # 类目为空/未知：用英文名里的类目词匹配（"trousers" / "scarf" …，去掉复数 s 也试）
        for key, val in CATEGORY_MAP.items():
            if re.search(rf"\b{key}\b|\b{key.rstrip('s')}\b", t):
                goods_type, style_zh = val
                break
    if not goods_type:
        goods_type, style_zh = TYPE_CLOTHING, "服装"
    for pat, group, zh in TITLE_REFINE:
        if group == goods_type and re.search(pat, t):
            style_zh = zh
            break
    return goods_type, _gender_label(goods_type, gender), style_zh


def build_toast_goods_name(code: str, size: str, style_category: str = "", title: str = "",
                           gender: str = "", brand_label: str = BRAND_LABEL) -> Tuple[str, str]:
    """返回 (货品名称, goods_type)，如 ("TOAST女装长裤WTRWW24INDI尺码8", "服装")"""
    goods_type, gender_label, style_zh = classify_toast_goods(style_category, title, gender)
    return f"{brand_label}{gender_label}{style_zh}{code}尺码{size}", goods_type


def get_package_spec(goods_type: str) -> Dict[str, int]:
    return PACKAGE_SPEC_BY_TYPE.get(goods_type, _DEFAULT_PACKAGE)


def fetch_toast_products(pgcfg: Dict, table: str = "toast_inventory") -> Dict[str, Dict[str, str]]:
    """
    product_code → {title, category, gender}。
    按编码取（不按尺码）：淘宝 SKU 尺码和库里尺码经常对不上（如 XL vs 4~18），品类/性别同编码都一样。
    """
    import psycopg2
    m: Dict[str, Dict[str, str]] = {}
    with psycopg2.connect(**pgcfg) as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT product_code, COALESCE(product_title,''), COALESCE(style_category,''), COALESCE(gender,'')
            FROM {table} ORDER BY id
        """)
        for code, title, cat, gender in cur.fetchall():
            if code and code not in m:
                m[str(code)] = {"title": title, "category": cat, "gender": gender}
    return m
