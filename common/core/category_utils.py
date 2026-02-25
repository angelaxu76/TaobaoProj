# common_taobao/core/category_utils.py
import re

# ===== Barbour 编码前缀 → 类别（尽量用通用英文类别，便于跨品牌复用）=====
# 说明：取前三位字母即可。若遇到新前缀，可在此处不断补充。
BARBOUR_PREFIX_MAP = {
    # Men
    "MWX": "waxed jacket",        # Men's Waxed Jacket
    "MQU": "quilted jacket",      # Men's Quilted Jacket
    "MLI": "gilet/liner",         # Men's Liner / Waistcoat
    "MSH": "shirt",               # Men's Shirt
    "MKN": "knitwear",            # Men's Knitwear / Jumper
    "MTS": "t-shirt",             # Men's T-shirt
    "MPQ": "quilted jacket",      # 有时使用 PQ 系列（可按需扩展）
    # Women
    "LWX": "waxed jacket",        # Women's Waxed Jacket
    "LQU": "quilted jacket",      # Women's Quilted Jacket
    "LLI": "gilet/liner",         # Women's Liner / Gilet
    "LSH": "shirt/blouse",        # Women's Shirt / Blouse
    "LKN": "knitwear",            # Women's Knitwear
    "LTS": "t-shirt",             # Women's T-shirt
    # Accessories (常见缩写，视实际数据补充)
    "UBA": "bag",                 # Barbour bags 行业常见前缀
    "UAC": "accessory",           # Accessories（通用）
    "USC": "scarf",               # Scarf（常见缩写）
    "MGL": "gloves",              # Men's Gloves
    "LGL": "gloves",              # Women's Gloves
}

# 服装+鞋类关键词匹配（name/desc 都会参与）
KEYWORD_RULES = [
    # 外套 & 马甲
    (r"\b(wax(ed)?|sylkoil)\b.*\bjacket\b",           "waxed jacket"),
    (r"\bquilt(ed|ing)?\b.*\bjacket\b",               "quilted jacket"),
    (r"\b(parka|anorak|waterproof|rain)\b.*\bjacket\b","waterproof jacket"),
    (r"\b(gilet|waistcoat|liner)\b",                  "gilet/liner"),
    (r"\b(bodywarmer)\b",                             "gilet/liner"),

    # 上装
    (r"\b(shirt|blouse)\b",                           "shirt/blouse"),
    (r"\b(t[\-\s]?shirt|tee)\b",                      "t-shirt"),
    (r"\b(polo)\b",                                   "polo"),
    (r"\b(knit|jumper|sweater|cardigan)\b",           "knitwear"),
    (r"\b(hoodie|sweatshirt)\b",                      "sweatshirt/hoodie"),

    # 下装
    (r"\b(trouser|pant|chino|jean)\b",                "trousers"),
    (r"\b(shorts)\b",                                 "shorts"),
    (r"\b(skirt)\b",                                  "skirt"),
    (r"\b(dress)\b",                                  "dress"),

    # 配件
    (r"\b(bag|holdall|backpack|tote|duffel)\b",       "bag"),
    (r"\b(scarf|wrap|stole)\b",                       "scarf"),
    (r"\b(glove|mitt(en)?)\b",                        "gloves"),
    (r"\b(hat|beanie|cap)\b",                         "hat"),

    # 鞋类（保留原有鞋类兜底分支，但移到后面，优先判断服装）
    (r"\b(boot)s?\b",                                 "boots"),
    (r"\b(sandal)s?\b",                               "sandal"),
    (r"\b(loafer)s?\b",                               "loafers"),
    (r"\bslip[\-\s]?on\b",                            "slip-on"),
]

def _from_barbour_code(product_code: str) -> str | None:
    if not product_code:
        return None
    m = re.match(r"([A-Z]{3})\d+", product_code.upper())
    if not m:
        # 也有少量是“字母+数字+字母”的形式，这里只取前三位字母做前缀
        m = re.match(r"([A-Z]{3})", product_code.upper())
    if not m:
        return None
    prefix = m.group(1)
    return BARBOUR_PREFIX_MAP.get(prefix)

def infer_style_category(
    desc: str = "",
    product_name: str = "",
    product_code: str = "",
    brand: str = "",
) -> str:
    """
    智能推断商品类别（向后兼容：只传 desc 也可用）
    优先级：
    1) 若 brand 是 Barbour 且能从 product_code 前缀命中 → 直接返回
    2) 关键词从 product_name + desc 综合判断
    3) 仍未命中 → 返回 'casual wear'（服装兜底）
       若 name/desc 明显包含鞋类再回落到 'casual shoes'
    """
    # 1) 条码前缀（Barbour）
    if brand and brand.lower() == "barbour":
        cat = _from_barbour_code(product_code)
        if cat:
            return cat

    text = f"{product_name or ''} {desc or ''}".lower()

    # 2) 关键词规则
    for pat, cat in KEYWORD_RULES:
        if re.search(pat, text):
            return cat

    # 3) 兜底：判断是否是鞋
    if any(k in text for k in ["boot", "sandal", "loafer", "slip on", "slip-on"]):
        return "casual shoes"
    return "casual wear"
