# color_utils.py

# 标准颜色映射（数据库中统一使用）
COLOR_MAP = {
    "black": "Black",
    "navy": "Navy",
    "blue": "Blue",
    "green": "Green",
    "olive": "Olive",
    "brown": "Brown",
    "tan": "Tan",
    "grey": "Grey",
    "gray": "Grey",
    "white": "White",
    "cream": "Cream",
    "silver": "Silver",
    "red": "Red",
    "pink": "Pink",
    "yellow": "Yellow",
    "mauve": "Mauve",
    "peach": "Peach",
    "beige": "Beige",
    "toast": "Beige",
    "camel": "Camel",
    "rust": "Rust",
    "plum": "Plum",
    "stone": "Stone",
    "salt": "Salt",
    "pearl": "Pearl",
    "cloud": "Silver",
    "envy": "Green",
    "floral": "Floral",
    "jaguar": "Beige",
    "empire": "Green",
    "birch": "Silver Birch",
    "steel": "Steel Blue",
    "sage": "Sage",
    "taupe": "Taupe",
    "sand": "Sand",
    "oyster": "Oyster Grey",
    "mist": "Mist",
    "archive": "Olive",
    "charcoal": "Charcoal",
    "bark": "Brown",
    "forest": "Green",
    "indigo": "Navy",
    "chrome": "Silver",
    "asphalt": "Grey",
    "calico": "Cream",
    "concrete": "Grey",
    "dove": "Grey",
    "leopard": "Animal Print",
    "trail": "Floral",
    "transparent": "Transparent",
    "flame": "Orange",
    "mandarin": "Orange",
    "yellow": "Yellow",
    "tobacco": "Brown",
    "thistle": "Purple",
    "redwood": "Red",
    "scarlet": "Red",
    "blanc": "White",
    "cumin": "Brown",
    "bordeaux": "Red",
    "pruce": "Green",  # 推测是 spruce 的拼写错误
    "bayleaf": "Green",  # 常见绿色调
}

# 修饰词（不是颜色本身）
STOP_WORDS = {
    "classic", "light", "pale", "dark", "high", "gloss", "deep", "dusty", "dusky",
    "neutral", "rich", "vintage", "warm", "cool", "bright", "soft", "washed", "ancient", "dress","Steel", "modern"
}

def normalize_color(raw_color: str) -> str:
    # 1. 如果是组合颜色，只保留第一个部分
    color = raw_color.split("/")[0].strip()

    # 2. 转小写 + 拆词
    words = color.lower().split()

    # 3. 移除修饰词
    keywords = [w for w in words if w not in STOP_WORDS]

    # 4. 关键词映射
    for word in keywords:
        if word in COLOR_MAP:
            return COLOR_MAP[word]

    # 5. fallback：保留第一个有效词，首字母大写
    return keywords[0].capitalize() if keywords else raw_color.strip()
