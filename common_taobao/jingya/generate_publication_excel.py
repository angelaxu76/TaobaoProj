import re
from pathlib import Path
from common_taobao.core.translate import safe_translate

# 材质提取优先级（英文关键词 -> 中文标签）
MATERIAL_PRIORITY_MAP = [
    ("小牛皮", ["calfskin", "full grain", "nappa", "leather"]),
    ("麂皮", ["nubuck", "suede", "velour"]),
    ("织物", ["textile", "fabric", "woven", "tencel", "lyocell"]),
    ("橡胶", ["rubber", "eva", "tpu"]),
    ("再生材料", ["recycled", "eco", "sustainable"]),
]

def extract_primary_material(text: str) -> str:
    lowered = text.lower()
    for label, keywords in MATERIAL_PRIORITY_MAP:
        if any(k in lowered for k in keywords):
            return label
    return ""

def extract_field(name: str, content: str) -> str:
    pattern = re.compile(rf"{name}\s*[:：]\s*(.+)", re.IGNORECASE)
    match = pattern.search(content)
    return match.group(1).strip() if match else ""

def generate_taobao_title(product_code: str, brand_key: str) -> str:
    from config import BRAND_CONFIG, BRAND_NAME_MAP

    brand_info = BRAND_CONFIG[brand_key.lower()]
    txt_folder: Path = brand_info["TXT_DIR"]
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key, brand_key))

    txt_file = txt_folder / f"{product_code}.txt"
    if not txt_file.exists():
        raise FileNotFoundError(f"❌ TXT 文件不存在: {txt_file}")

    content = txt_file.read_text(encoding="utf-8")
    title_en = extract_field("Product Name", content)
    feature_str = extract_field("Feature", content) + " " + extract_field("Product Description", content)
    material_en = extract_field("Product Material", content) + " " + feature_str

    # 提取系列名（前1-2个词）
    style_name = title_en.strip().split()[0] if title_en else ""
    # 提取颜色（简单规则）
    color_match = re.search(r"(Black|White|Brown|Red|Blue|Grey|Gray|Pink|Green|Beige|Yellow|Burgundy|Navy)", title_en, re.IGNORECASE)
    color_cn = safe_translate(color_match.group(1)) if color_match else ""

    # 提取主材质
    material_cn = extract_primary_material(material_en)

    # 功能描述提取（部分关键词）
    feature_keywords = [
        ("EVA", "EVA大底"),
        ("XL EXTRALIGHT", "轻盈缓震"),
        ("OrthoLite", "高弹鞋垫"),
        ("增高", "增高")
    ]
    features = []
    for k, label in feature_keywords:
        if k.lower() in feature_str.lower():
            features.append(label)

    # 构造标题结构
    gender_cn = "女鞋"  # 暂定默认，如后续支持自动识别可扩展
    feature_part = "".join(features)

    parts = [
        f"{brand_en}/{brand_cn}",
        gender_cn,
        style_name,
        color_cn,
        material_cn,
        feature_part,
        product_code
    ]
    title = "".join(filter(None, parts))

    # 淘宝标题长度控制（58-60 字）
    if len(title) > 60 and feature_part:
        title = title.replace(feature_part, "")
    if len(title) > 60:
        title = title[:60]

    return title
