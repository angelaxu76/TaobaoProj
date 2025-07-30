import re
from config import BRAND_NAME_MAP
from common_taobao.core.translate import safe_translate

COLOR_MAP = {
    "White": "白色", "Black": "黑色", "Blue": "蓝色", "Red": "红色",
    "Brown": "棕色", "Beige": "米色", "Green": "绿色", "Grey": "灰色",
    "Yellow": "黄色", "Pink": "粉色", "Orange": "橙色", "Purple": "紫色"
}

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

def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    from common_taobao.generate_taobao_title import get_byte_length, truncate_to_max_bytes

    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    title_en = extract_field_from_content(content, "Product Name")
    material_en = extract_field_from_content(content, "Product Material")
    color_en = extract_field_from_content(content, "Product Color")
    gender_raw = extract_field_from_content(content, "Product Gender") or "女款"
    style_name = title_en.split()[0].capitalize() if title_en else "系列"

    color_cn = COLOR_MAP.get(color_en, color_en)
    material_cn = get_primary_material_cn(material_en)
    gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}.get(gender_raw, "鞋")

    features = extract_features_from_content(content)
    banned = ["最", "唯一", "首个", "国家级", "世界级", "顶级"]
    features_str = " ".join([f for f in features if not any(b in f for b in banned)])

    base_title = f"{brand_full}{gender_str}{style_name}{color_cn}{material_cn}{features_str}{product_code}".strip()

    max_bytes = 60  # 淘宝计算中文一个字符两个字节

    # 如果超长，先裁掉 features
    if get_byte_length(base_title) > max_bytes:
        base_title = f"{brand_full}{gender_str}{style_name}{color_cn}{material_cn}{product_code}".strip()

    # 如果仍不足 60 字节，补充流量词
    filler_words = ["新款", "百搭", "舒适", "潮流", "轻奢", "经典"]
    for word in filler_words:
        new_title = base_title + word
        if get_byte_length(new_title) <= max_bytes:
            base_title = new_title
        else:
            break

    return {
        "title_cn": base_title,
        "taobao_title": base_title
    }

