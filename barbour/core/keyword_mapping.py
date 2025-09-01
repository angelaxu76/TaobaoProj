KEYWORD_EQUIVALENTS = [
    {"wax", "waxed"},
    {"hood", "hooded"},
    {"trench", "trenchcoat", "trench coat"},
    {"bomber", "bomberjacket", "bomber jacket"},
    {"longline", "long"},
    {"gilet", "waistcoat","vest"},
    {"quilt", "quilted"},
    {"coat", "jacket"},  # 可选，根据实际你 barbour_products 的风格定义调整
    {"overshirt", "shirt"},
    {"anorak", "parka"},
    {"fleece", "sweater"},
]

# 关键词等价表（保持你现有的）
KEYWORD_EQUIVALENTS = globals().get("KEYWORD_EQUIVALENTS", {})

# ==== 集中维护停用词（高频无区分词） ====
STOPWORDS = {
    "barbour", "international", "jacket", "waterproof",
    "coat", "coats", "overshirt",
    "men", "mens", "women", "womens", "kids", "boys", "girls",
}