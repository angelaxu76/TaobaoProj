import re
from pathlib import Path
from config import BRAND_CONFIG
from common_taobao.core.translate import safe_translate

# ✅ 材质和颜色映射（可持续扩充）
MATERIAL_MAP = {
    "Calfskin": "小牛皮",
    "Leather": "牛皮",
    "Nubuck": "磨砂皮",
    "Suede": "反毛皮",
    "Textile": "织物",
    "Canvas": "帆布",
    "Polyester": "聚酯纤维",
    "Mesh": "网布",
    "Rubber": "橡胶",
    "EVA": "EVA"
}

COLOR_MAP = {
    "Black": "黑色",
    "White": "白色",
    "Brown": "棕色",
    "Navy": "藏青",
    "Beige": "米色",
    "Green": "绿色",
    "Red": "红色",
    "Yellow": "黄色",
    "Grey": "灰色",
    "Blue": "蓝色"
}

# ✅ 去重材质函数
def deduplicate_material(material_list):
    result = []
    seen = set()
    leather_keywords = {"牛皮", "小牛皮", "磨砂皮", "反毛皮"}
    for m in material_list:
        if m in seen:
            continue
        if m in leather_keywords and any(x in result for x in leather_keywords):
            continue
        result.append(m)
        seen.add(m)
    return result

# ✅ 从TXT中提取字段
def extract_field(name, content):
    pattern = re.compile(rf"{name}\s*[:：]\s*(.+)", re.IGNORECASE)
    match = pattern.search(content)
    return match.group(1).strip() if match else ""

# ✅ 主函数：传入品牌名和商品编码，返回淘宝标题
def generate_taobao_title(brand: str, product_code: str) -> str:
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")
    config = BRAND_CONFIG[brand]
    txt_folder: Path = config["TXT_DIR"]
    txt_path = txt_folder / f"{product_code.upper()}.txt"

    if not txt_path.exists():
        raise FileNotFoundError(f"❌ TXT 文件不存在: {txt_path}")

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    title_en = extract_field("Product Name", content)
    brand_en = title_en.split()[0] if title_en else brand.upper()
    brand_cn = "看步" if brand == "camper" else "未知品牌"
    brand_full = f"{brand_en}/{brand_cn}"

    # 提取样式名
    style_match = re.search(r"\b([A-Z][a-zA-Z]+)\b", product_code)
    style_name = style_match.group(1) if style_match else ""

    # 提取颜色和材质
    color_en = extract_field("Colour", content)
    material_en = extract_field("Product Material", content)

    color_cn = COLOR_MAP.get(color_en.strip().title(), color_en.strip())
    material_parts = re.split(r"[ /,]+", material_en.strip())
    material_cn_list = [MATERIAL_MAP.get(m.strip(), m.strip()) for m in material_parts if m]
    material_cn_list = deduplicate_material(material_cn_list)
    material_cn = "、".join(material_cn_list)

    # 翻译特征（如 feature、描述等字段）
    features_raw = extract_field("Feature", content)
    features = [f.strip() for f in re.split(r"[|｜]", features_raw) if f.strip()]
    features_cn = [safe_translate(f) for f in features]
    features_cn = [f for f in features_cn if not any(b in f for b in ["最", "唯一", "国家级", "顶级", "第一"])]

    # 构建基础标题
    gender = "女鞋" if "女性" in content.lower() or "女" in content.lower() else "男鞋"
    base = f"{brand_full}{gender}{style_name}{color_cn}{material_cn}"
    suffix = product_code.upper()
    full_title = f"{base}{''.join(features_cn)}{suffix}"

    # 控制字数不超过 60 字
    while len(full_title) > 60 and features_cn:
        features_cn.pop()
        full_title = f"{base}{''.join(features_cn)}{suffix}"

    if len(full_title) > 60:
        full_title = full_title[:60]

    return full_title
