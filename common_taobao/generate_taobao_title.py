import re
from config import BRAND_NAME_MAP
import random
from common_taobao.core.translate import safe_translate

COLOR_MAP = {
    "black": "黑色", "white": "白色", "red": "红色", "navy": "深蓝色", "tan": "浅棕色",
    "brown": "棕色", "blue": "蓝色", "grey": "灰色", "green": "绿色", "olive": "橄榄绿",
    "pink": "粉色", "burgundy": "酒红色", "beige": "米色", "cream": "奶油色",
    "silver": "银色", "gold": "金色", "stone": "石灰色", "orange": "橙色",
    "plum": "梅子色", "taupe": "灰褐色", "cola": "可乐色", "off white": "米白色",
    "pewter": "锡色", "rust": "铁锈红", "light tan": "浅棕褐", "dark tan": "深棕褐"
}

color_keywords = [
    "black", "tan", "navy", "brown", "white", "grey", "off white", "blue",
    "silver", "olive", "cream", "red", "green", "beige", "cola", "pink",
    "burgundy", "taupe", "stone", "bronze", "orange", "walnut", "pewter",
    "plum", "yellow", "rust"
]

MATERIAL_MAP = {
    "Calfskin": "小牛皮", "Leather": "牛皮", "Nubuck": "磨砂皮", "Textile": "织物",
    "Suede": "反毛皮", "Canvas": "帆布", "Mesh": "网布", "Synthetic": "合成材质"
}


def get_primary_material_cn(material_en: str) -> str:
    parts = re.split(r"[ /,|]+", material_en)
    for part in parts:
        part_clean = part.strip().capitalize()
        if part_clean in MATERIAL_MAP:
            return MATERIAL_MAP[part_clean]
    return parts[0] if parts else "材质未知"


def extract_field_from_content(content: str, field: str) -> str:
    pattern = re.compile(rf"{field}[:：]?\s*(.+)", re.IGNORECASE)
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def extract_features_from_content(content: str) -> list[str]:
    features = []
    content_lower = content.lower()
    if "eva" in content_lower: features.append("EVA大底")
    if "light" in content_lower: features.append("轻盈缓震")
    if "extra height" in content_lower or "3cm" in content_lower: features.append("增高")
    if "sneaker" in content_lower or "runner" in content_lower: features.append("复古慢跑鞋")
    if "recycled" in content_lower: features.append("环保材质")
    if "rubber" in content_lower: features.append("防滑橡胶底")
    if "ballet" in content_lower: features.append("芭蕾风")
    if "removable" in content_lower: features.append("可拆鞋垫")
    return features


def determine_shoe_type(title: str, content: str) -> str:
    t = title.lower()
    c = content.lower()
    if any(k in t or k in c for k in ["boot", "chelsea", "ankle"]):
        return "短靴"
    if any(k in t or k in c for k in ["sandal", "slide", "slipper", "mule", "flip-flop"]):
        return "凉鞋"
    return "休闲鞋"


def get_byte_length(text: str) -> int:
    return len(text.encode("gbk", errors='ignore'))


def truncate_to_max_bytes(text: str, max_bytes: int) -> str:
    result = ''
    total = 0
    for char in text:
        char_len = len(char.encode("gbk", errors='ignore'))
        if total + char_len > max_bytes:
            break
        result += char
        total += char_len
    return result


FILLER_WORDS = [
    "新款", "百搭", "舒适", "潮流", "轻奢", "经典", "时尚", "复古",
    "透气", "柔软", "减震", "轻盈", "耐穿", "通勤", "日常", "不磨脚",
    "支撑感强", "贴合脚型", "不累脚", "细腻", "驾车",
    "休闲", "逛街", "出街", "回购", "简约", "英伦"
]


def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    title_en = extract_field_from_content(content, "Product Name")
    material_en = extract_field_from_content(content, "Product Material")
    color_en = extract_field_from_content(content, "Product Color")
    gender_raw = extract_field_from_content(content, "Product Gender") or "女款"

    # 提取 Clarks 款式名称：查找颜色关键词并从其中分离前缀

    # Clarks 款式名提取：取 gender 和 color 之间的词
    style_name = ""
    if brand_key.lower().startswith("clarks") and title_en:
        title_en_lower = title_en.lower()
        gender_keywords = ["womens", "mens", "kids", "girls", "boys"]
        for gender in gender_keywords:
            for color in color_keywords:
                pattern = rf"{gender}\s+(.*?)\s+{color}"
                match = re.search(pattern, title_en_lower)
                if match:
                    style_name = match.group(1).strip().title()
                    break
            if style_name:
                break
    if not style_name:
        style_name = title_en.split()[0].capitalize() if title_en else "系列"

    color_en_clean = (color_en or "").strip().lower()

    # ✅ 只有 Product Color 原始字段为空时，才从标题中自动识别颜色
    if not color_en or not color_en.strip():
        title_lower = (title_en or "").lower()
        for color in color_keywords:
            if color in title_lower:
                color_en_clean = color
                break

    color_cn = COLOR_MAP.get(color_en_clean, color_en_clean)

    material_cn = get_primary_material_cn(material_en)
    gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}.get(gender_raw, "鞋")

    features = extract_features_from_content(content)
    banned = ["最", "唯一", "首个", "国家级", "世界级", "顶级"]
    features_str = " ".join([f for f in features if not any(b in f for b in banned)])
    type = determine_shoe_type(title_en, content)

    # 拼接主干标题
    base_title = f"{brand_full}{gender_str}{style_name}{type}{color_cn}{material_cn}{features_str}".strip()
    base_title = base_title.replace("No Data", "")

    # 裁剪逻辑：先去掉 features 确保不过长
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{style_name}{color_cn}{material_cn}".strip()

    # 如仍不足60，可随机补充流量词
    if get_byte_length(base_title) < 60:
        available_bytes = 60 - get_byte_length(base_title)

        # 随机打乱并挑选最多3个词补充（依次追加，直到满）
        random.shuffle(FILLER_WORDS)
        for word in FILLER_WORDS:
            word_bytes = get_byte_length(word)
            if available_bytes >= word_bytes:
                base_title += word
                available_bytes -= word_bytes
            else:
                break

    return {
        "title_cn": base_title,
        "taobao_title": base_title
    }


