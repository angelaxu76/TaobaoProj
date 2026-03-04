# common/product/style_category_normalizer.py
"""
服装 Style Category 规范化工具。

各品牌 fetch 脚本在写 TXT 时调用 normalize_style_category()，
确保 Style Category 字段统一为固定英文 canonical key，
便于跨品牌 Excel 脚本（generate_publication_excel_outerwear）直接复用。

Canonical set（与 determine_category_cn() 的 mapping 一一对应）:
    Jackets / Knitwear / Sweatshirts / Dresses / Jumpsuits
    Shirts / Tops / Trousers / Skirts / Shorts / Lingerie / Other
"""

# ── Canonical key → 中文显示 ────────────────────────────────────────────────
CANONICAL_CATEGORIES: dict[str, str] = {
    "Jackets":     "外套",
    "Knitwear":    "针织衫",
    "Sweatshirts": "卫衣",
    "Dresses":     "连衣裙",
    "Jumpsuits":   "连体裤",
    "Shirts":      "衬衫",
    "Tops":        "上衣",
    "Trousers":    "长裤",
    "Skirts":      "半身裙",
    "Shorts":      "短裤",
    "Lingerie":    "内衣",
    "Other":       "服装",
}

# ── 原始值 → canonical key（大小写不敏感，用 lower key 查找）──────────────────
# 包含：英文网站原始值、M&S 旧中文值（向后兼容已有 TXT）
_ALIAS_MAP: dict[str, str] = {
    # ---- 外套 ----
    "coat":          "Jackets",
    "coats":         "Jackets",
    "jacket":        "Jackets",
    "jackets":       "Jackets",
    "blazer":        "Jackets",
    "blazers":       "Jackets",
    "waistcoat":     "Jackets",
    "waistcoats":    "Jackets",
    "gilet":         "Jackets",
    "gilets":        "Jackets",
    "parka":         "Jackets",
    "parkas":        "Jackets",
    "puffer":        "Jackets",
    "outerwear":     "Jackets",
    # ---- 针织衫 ----
    "knitwear":      "Knitwear",
    "jumper":        "Knitwear",
    "jumpers":       "Knitwear",
    "sweater":       "Knitwear",
    "sweaters":      "Knitwear",
    "cardigan":      "Knitwear",
    "cardigans":     "Knitwear",
    "pullover":      "Knitwear",
    # ---- 卫衣 ----
    "sweatshirt":    "Sweatshirts",
    "sweatshirts":   "Sweatshirts",
    "hoodie":        "Sweatshirts",
    "hoodies":       "Sweatshirts",
    "fleece":        "Sweatshirts",
    # ---- 连衣裙 ----
    "dress":         "Dresses",
    "dresses":       "Dresses",
    "kaftan":        "Dresses",
    # ---- 连体裤 ----
    "jumpsuit":      "Jumpsuits",
    "jumpsuits":     "Jumpsuits",
    "playsuit":      "Jumpsuits",
    "playsuits":     "Jumpsuits",
    # ---- 衬衫 ----
    "shirt":         "Shirts",
    "shirts":        "Shirts",
    "blouse":        "Shirts",
    "blouses":       "Shirts",
    "polo":          "Shirts",
    # ---- 上衣 ----
    "top":           "Tops",
    "tops":          "Tops",
    "t shirt":       "Tops",
    "t shirts":      "Tops",
    "tee":           "Tops",
    "tees":          "Tops",
    # ---- 长裤 ----
    "trouser":       "Trousers",
    "trousers":      "Trousers",
    "pant":          "Trousers",
    "pants":         "Trousers",
    "jean":          "Trousers",
    "jeans":         "Trousers",
    # ---- 半身裙 ----
    "skirt":         "Skirts",
    "skirts":        "Skirts",
    # ---- 短裤 ----
    "short":         "Shorts",
    "shorts":        "Shorts",
    # ---- 内衣 ----
    "lingerie":      "Lingerie",
    "underwear":     "Lingerie",
    "bra":           "Lingerie",
    "bras":          "Lingerie",
    # ---- M&S 旧中文值（向后兼容已有 TXT） ----
    "上衣/外套":      "Jackets",
    "上衣/针织":      "Knitwear",
    "上衣/卫衣":      "Sweatshirts",
    "连衣裙":         "Dresses",
    "上衣/衬衫":      "Shirts",
    "上衣/其他":      "Other",
    "内衣/文胸":      "Lingerie",
}

# ── 关键词推断规则（product_name 无法在 _ALIAS_MAP 命中时使用）────────────────
# 按匹配优先级排列，更具体的关键词放前面
_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["shacket", "anorak", "trucker", "mac ", " mac", "bomber",
      "coach jacket", "parka", "gilet", "waistcoat",
      "blazer", "jacket", "coat"],                           "Jackets"),
    (["cardigan", "jumper", "knitwear", "pullover",
      "sweater", "knit"],                                    "Knitwear"),
    (["sweatshirt", "hoodie", "hoody", "fleece"],            "Sweatshirts"),
    (["kaftan", "playsuit", "jumpsuit"],                     "Jumpsuits"),
    (["dress"],                                              "Dresses"),
    (["polo", "rugby", "overshirt", "blouse", "shirt"],      "Shirts"),
    (["t-shirt", "tee"],                                     "Tops"),
    (["trouser", "pant", "jean"],                            "Trousers"),
    (["skirt"],                                              "Skirts"),
    (["short"],                                              "Shorts"),
    (["bra ", " bra", "lingerie", "underwear"],              "Lingerie"),
]


def normalize_style_category(raw: str, product_name: str = "") -> str:
    """
    将原始 Style Category 值规范化为固定英文 canonical key。

    Args:
        raw:          网站返回的原始 style_category 字符串（可为空）。
        product_name: 商品英文名称，用于关键词兜底推断。

    Returns:
        canonical key，例如 "Jackets"、"Knitwear"、"Dresses" 等。
        无法判断时返回 "Other"。

    Examples:
        >>> normalize_style_category("coats")          # → "Jackets"
        >>> normalize_style_category("上衣/针织")       # → "Knitwear"
        >>> normalize_style_category("", "Slim Fit Hoodie Sweatshirt")  # → "Sweatshirts"
    """
    # 1. 直接查 alias map（先原始大小写，再 lowercase）
    if raw:
        raw_stripped = raw.strip()
        key = _ALIAS_MAP.get(raw_stripped) or _ALIAS_MAP.get(raw_stripped.lower())
        if key:
            return key
        # 已经是 canonical key 则直接返回
        if raw_stripped in CANONICAL_CATEGORIES:
            return raw_stripped

    # 2. 关键词推断（product_name）
    if product_name:
        name_lower = product_name.lower()
        for keywords, category in _KEYWORD_RULES:
            if any(kw in name_lower for kw in keywords):
                return category

    return "Other"
