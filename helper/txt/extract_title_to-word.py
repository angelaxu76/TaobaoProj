import re
from pathlib import Path

# ======================
# 路径配置（注意 Windows 路径）
# ======================

INPUT_FILE = r"C:\Users\martin\Desktop\title.txt"
OUTPUT_FILE = r"C:\Users\martin\Desktop\keywords_style_only.txt"


# ======================
# 1. 停用词定义（重点）
# ======================

# 通用无意义词
STOPWORDS_COMMON = {
    "the", "and", "or", "with", "for", "of", "in", "on",
    "by", "to", "from", "this", "that", "these", "those",
    "new", "not", "all"
}

# 性别词
STOPWORDS_GENDER = {
    "men", "mens", "man", "male",
    "women", "womens", "woman", "female",
    "boy", "boys", "girl", "girls",
    "kids", "kid", "child", "children",
    "unisex", "ladies", "lady"
}

# 类目 / 商品类型词（强过滤）
STOPWORDS_CATEGORY = {
    # 外套 / 上装
    "jacket", "jackets", "coat", "coats", "parka", "anorak",
    "blazer", "bomber", "overcoat", "overshirt", "duffle",
    "smock", "trench", "waistcoat", "gilet", "gilets", "vest",

    # 下装 / 套装
    "trouser", "trousers", "pants", "jeans", "leggings",
    "shorts", "skirt", "tracksuit",

    # 鞋 / 配饰
    "boot", "boots", "shoe", "shoes", "slipper", "slippers",
    "sandals", "trainer", "trainers",
        "bag","bags","backpack","belt","wallet","purse","tote",
    "umbrella","hat","hats","cap","caps","beanie","beret",
    "scarf","scarves","glove","gloves","socks","stockings",
    "shirt","shirts","tee","tshirt","top","tops",
    "jumper","sweater","sweatshirt","sweatshirts","hoodie",
    "cardigan","knit","knitted",
    "jeans","denim","trousers","trouser","pants","shorts",
    "skirt","dress","dresses",
}

# 服装结构 / 功能词
STOPWORDS_FEATURE = {
    "quilted", "quilt", "wax", "waxed", "padded", "lined",
    "liner", "insulated", "lightweight", "waterproof",
    "showerproof", "windproof", "detachable", "reversible",
    "removable", "hood", "hooded", "collared", "collarless",
    "zip", "zipper", "button", "buttons", "pocket", "pockets",
        "collar","stand","fit","fitted","sleeve","sleeves",
    "sleeved","sleeveless","zippered","zipped",
    "length","lined","lining","inner","outer",
}

# 版型 / 营销词
STOPWORDS_MARKETING = {
    "classic", "modern", "vintage", "heritage",
    "original", "originals", "signature", "essential",
    "essentials", "premium", "casual", "smart",
    "relaxed", "tailored", "regular", "slim",
    "oversized", "longline", "cropped",
}

# 颜色词（统一过滤）
STOPWORDS_COLOR = {
    "black", "navy", "olive", "green", "brown", "white",
    "grey", "gray", "khaki", "beige", "cream", "stone",
    "sage", "rust", "pink", "blue", "silver", "gold",
    "charcoal", "camel",
}

# 品牌词（无区分度）
STOPWORDS_BRAND = {
    "barbour", "international"
}
# ======================
# L2 层：描述 / 材质 / 季节 / 风格词（必须过滤）
# ======================

STOPWORDS_L2 = {
    # 风格 / 抽象描述
    "style","classic","modern","vintage","heritage","original","signature",
    "essential","premium","preppy","casual","smart","relaxed","rugged",
    "sport","sports","utility","uniform",

    # 材质 / 面料
    "suede","leather","cotton","wool","canvas","denim","linen","nubuck",
    "cashmere","merino","nylon","corduroy","tweed","velvet","satin","silk",
    "fleece","fur","microfleece","softshell","lambswool","moleskin",

    # 季节 / 场景
    "summer","winter","spring","autumn","fall","seasonal",
    "warm","cool","weather","outdoor","travel","weekender",

    # 功能（非结构）
    "waterproof","showerproof","windproof","resistant","breathable",
    "durable","technical","performance",

    # 版型 / 穿着感
    "fit","fitted","tailored","regular","slim","oversized",
    "long","short","cropped","length",

    # 图案 / 表现形式
    "pattern","patterned","print","printed","stripe","striped",
    "plaid","check","checked","herringbone","houndstooth",
    "texture","textured",
}


# 合并所有停用词
STOPWORDS_ALL = (
    STOPWORDS_COMMON
    | STOPWORDS_GENDER
    | STOPWORDS_CATEGORY
    | STOPWORDS_FEATURE
    | STOPWORDS_MARKETING
    | STOPWORDS_COLOR
    | STOPWORDS_BRAND
    | STOPWORDS_L2
)

MIN_WORD_LENGTH = 3


# ======================
# 2. 工具函数
# ======================

def normalize_word(word: str) -> str:
    word = word.lower()
    word = re.sub(r"[^a-z]", "", word)
    return word


def is_valid_word(word: str) -> bool:
    if len(word) < MIN_WORD_LENGTH:
        return False
    if word in STOPWORDS_ALL:
        return False
    # 兜底规则：明显不像款式名的直接丢
    if word.endswith(("ed", "ing", "ly")):
        return False
    return True



# ======================
# 3. 主处理逻辑
# ======================

def extract_style_keywords(input_file: str, output_file: str):
    keywords = set()
    lines = Path(input_file).read_text(encoding="utf-8").splitlines()

    for line in lines:
        parts = re.split(r"[\s\-_/]+", line)
        for p in parts:
            w = normalize_word(p)
            if not w:
                continue
            if is_valid_word(w):
                keywords.add(w)

    sorted_keywords = sorted(keywords)

    Path(output_file).write_text(
        "\n".join(sorted_keywords),
        encoding="utf-8"
    )

    print("✅ 处理完成")
    print(f"   原始标题数: {len(lines)}")
    print(f"   最终保留关键词数: {len(sorted_keywords)}")
    print(f"   输出文件: {output_file}")


# ======================
# 4. 入口
# ======================

if __name__ == "__main__":
    extract_style_keywords(INPUT_FILE, OUTPUT_FILE)
