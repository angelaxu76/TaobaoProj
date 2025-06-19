
SHOE_KEYWORDS = {
    "靴子": ["boot", "chelsea", "ankle", "desert"],
    "凉鞋": ["sandal", "slide", "flip flop", "slipper"],
    "休闲鞋": ["loafer", "sneaker", "trainer", "oxford", "derby"]
}

CLOTHING_KEYWORDS = {
    "T恤": ["t-shirt", "tee"],
    "衬衣": ["shirt", "button-down"],
    "夹克": ["jacket", "blazer"],
    "羽绒服": ["down", "puffer", "parka"]
}

def classify_product(text: str, brand_type: str) -> str:
    text = text.lower()
    if brand_type == "shoes":
        for label, keywords in SHOE_KEYWORDS.items():
            if any(k in text for k in keywords):
                return label
        return "其他鞋"
    elif brand_type == "clothing":
        for label, keywords in CLOTHING_KEYWORDS.items():
            if any(k in text for k in keywords):
                return label
        return "其他服饰"
    else:
        return "未分类"
