# -*- coding: utf-8 -*-
"""
专用：外套（coats / jackets / blazers / gilets / parkas / puffers）
品牌：REISS / Barbour（也可用于其它服装品牌）
接口保持与鞋类脚本一致：
    generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict
返回：
    {"title_cn": "...", "taobao_title": "..."}  # 60GBK字节内
"""
import re
import random
from config import BRAND_NAME_MAP

# ===== 颜色映射（可按需扩充） =====
COLOR_MAP = {
    "black":"黑色","white":"白色","red":"红色","navy":"深蓝色","tan":"浅棕色",
    "brown":"棕色","blue":"蓝色","grey":"灰色","gray":"灰色","green":"绿色",
    "olive":"橄榄绿","pink":"粉色","burgundy":"酒红色","beige":"米色","cream":"奶油色",
    "camel":"驼色","mocha":"摩卡色","chocolate":"巧克力色","stone":"石灰色","orange":"橙色",
    "purple":"紫色","plum":"梅子色","taupe":"灰褐色","gold":"金色","silver":"银色",
    "khaki":"卡其色","charcoal":"炭灰","ivory":"象牙白","coffee":"咖色",
}
COLOR_KEYWORDS = list(COLOR_MAP.keys())

# ===== 面料映射（服装向） =====
FABRIC_MAP = {
    "wax":"蜡质处理","waxed":"蜡质处理","waxed cotton":"蜡棉","cotton":"棉",
    "organic cotton":"有机棉","wool":"羊毛","cashmere":"羊绒","merino":"美丽诺羊毛",
    "leather":"皮革","suede":"麂皮","shearling":"羊羔毛","polyester":"聚酯",
    "nylon":"尼龙","viscose":"粘胶","linen":"亚麻","down":"羽绒","goose down":"鹅绒",
    "duck down":"鸭绒","recycled":"再生纤维",
}

# ===== 标题辅助 =====
FILLER_WORDS = [
    "秋冬","通勤","百搭","显瘦","廓形","质感","保暖","防风","防水","抗皱","易打理","英伦","经典",
]

# ===== 基础工具 =====
def get_byte_length(text: str) -> int:
    return len(text.encode("gbk", errors="ignore"))

def truncate_to_max_bytes(text: str, max_bytes: int) -> str:
    res, total = "", 0
    for ch in text:
        l = len(ch.encode("gbk", errors="ignore"))
        if total + l > max_bytes:
            break
        res += ch
        total += l
    return res

def extract_field_from_content(content: str, field: str) -> str:
    # 从 TXT 文本中抽取字段（与鞋类脚本同形）
    # 例：Product Color: Navy
    m = re.search(rf"{field}\s*[:：]\s*(.+)", content, flags=re.I)
    return m.group(1).strip() if m else ""

# ===== 识别外套类型（中文） =====
def determine_outerwear_type(title_en: str, content: str, style_cat: str) -> str:
    t = (title_en or "").lower()
    c = (content or "").lower()
    s = (style_cat or "").lower()
    blob = " ".join([t, c, s])

    if re.search(r"\btrench|mac|raincoat\b", blob): return "风衣"
    if re.search(r"\b(parka)\b", blob): return "派克"
    if re.search(r"\b(bomber)\b", blob): return "飞行员夹克"
    if re.search(r"\b(blazer|tailor(?:ed)?\s+jacket)\b", blob): return "西装外套"
    if re.search(r"\b(gilet|waistcoat)\b", blob): return "马甲"
    if re.search(r"\b(puffer|down|quilt(?:ed)?|padded)\b", blob): return "羽绒/绗缝"
    if re.search(r"\b(suede).*jacket|jacket.*\bsuede\b", blob): return "麂皮夹克"
    if re.search(r"\b(biker|moto|aviator|shearling).*jacket|jacket.*\bleather\b|\bleather\b.*jacket", blob): return "皮夹克"
    if re.search(r"\bovercoat\b", blob): return "大衣"
    if re.search(r"\bcoat\b", blob): return "大衣"
    if re.search(r"\bjacket\b", blob): return "夹克"
    return "外套"

# ===== 提取样式名（英文标题里去掉品牌/颜色/通用词后的首个词） =====
def extract_style_name(title_en: str, brand_key: str) -> str:
    if not title_en:
        return "系列"
    t = re.sub(r"[-_/]", " ", title_en).strip()
    t_low = t.lower()

    # 去掉品牌词
    brand = brand_key.lower()
    t_low = re.sub(rf"\b{re.escape(brand)}\b", "", t_low)

    # 去掉颜色词
    for col in COLOR_KEYWORDS:
        t_low = re.sub(rf"\b{re.escape(col)}\b", "", t_low)

    # 去掉通用外套词
    generic = [
        "women","womens","woman","men","mens","man","girls","boys",
        "coat","coats","jacket","jackets","blazer","blazers","gilet","gilets",
        "waistcoat","waistcoats","parka","parkas","bomber","bombers","down","puffer",
        "quilted","padded","trench","mac","raincoat","overcoat","outerwear",
    ]
    for g in generic:
        t_low = re.sub(rf"\b{g}\b", "", t_low)

    # 挑第一个可读 token
    tokens = [w for w in re.split(r"\s+", t_low) if w]
    if not tokens:
        return "系列"
    return tokens[0].capitalize()

# ===== 识别材质（中文主材质） =====
def get_primary_fabric_cn(material_en: str) -> str:
    text = (material_en or "").lower()
    parts = re.split(r"[ /,|]+", text)
    for p in parts:
        if p in FABRIC_MAP:
            return FABRIC_MAP[p]
    # 关键词匹配（例如标题/描述里出现）
    for k, v in FABRIC_MAP.items():
        if k in text:
            return v
    return "面料"

# ===== 提取卖点（外套向） =====
def extract_outerwear_features(content: str) -> list[str]:
    c = (content or "").lower()
    feats = []

    # Barbour 常见
    if "wax" in c or "waxed" in c: feats.append("蜡棉")
    if "cord collar" in c or "corduroy" in c: feats.append("灯芯绒领")
    if "tartan" in c or "lined" in c: feats.append("格纹内衬")

    # 机能/保暖
    if "waterproof" in c or "water-resistant" in c or "water resistant" in c: feats.append("防水")
    if "windproof" in c: feats.append("防风")
    if "breathable" in c: feats.append("透气")
    if "down" in c or "puffer" in c or "fill" in c or "insulated" in c: feats.append("保暖")
    if "lightweight" in c: feats.append("轻量")
    if "quilt" in c or "padded" in c: feats.append("绗缝")

    # 版型/细节
    if "belt" in c or "belted" in c: feats.append("系带")
    if "double-breasted" in c: feats.append("双排扣")
    if "detachable hood" in c or "hood" in c: feats.append("连帽")

    # 去重 & 过滤夸张词
    banned = ["最","唯一","首个","顶级","世界级","国家级"]
    feats = [f for f in dict.fromkeys(feats) if not any(b in f for b in banned)]
    return feats

# ===== 主函数（与鞋类脚本同名/同签名） =====
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get(brand_key.lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    title_en  = extract_field_from_content(content, "Product Name")
    material  = extract_field_from_content(content, "Product Material")
    color_en  = extract_field_from_content(content, "Product Color")
    gender_in = extract_field_from_content(content, "Product Gender")
    style_cat = extract_field_from_content(content, "Style Category")

    # 性别：外套用“女装/男装”
    gender_label = "女装"
    if gender_in:
        gl = gender_in.strip().lower()
        if gl.startswith("men"): gender_label = "男装"
        elif gl.startswith("women"): gender_label = "女装"

    # 颜色（优先字段，其次标题猜测）
    color_key = (color_en or "").strip().lower()
    if not color_key:
        t_low = (title_en or "").lower()
        for ck in COLOR_KEYWORDS:
            if ck in t_low:
                color_key = ck
                break
    color_cn = COLOR_MAP.get(color_key, color_key or "")

    # 材质（中文主材）
    fabric_cn = get_primary_fabric_cn(material)

    # 外套类型（中文）
    outer_type = determine_outerwear_type(title_en, content, style_cat)

    # 样式名（英文名做中文标题的“系列词”）
    style_name = extract_style_name(title_en, brand_key)

    # 组合卖点
    features = extract_outerwear_features(content)
    feat_str = "".join(features)

    # === 拼接主标题：控制在 60 GBK 字节 ===
    base = f"{brand_full}{gender_label}{style_name}{outer_type}{color_cn}{fabric_cn}{feat_str}".strip()
    base = base.replace("No Data","").replace("面料","").strip()

    # 裁剪策略：先去掉卖点，再去掉材质，最后硬截断
    if get_byte_length(base) > 60 and feat_str:
        base = base.replace(feat_str, "").strip()
    if get_byte_length(base) > 60 and fabric_cn:
        base = base.replace(fabric_cn, "").strip()
    if get_byte_length(base) > 60:
        base = truncate_to_max_bytes(base, 60)

    # 不足则补充轻量词
    if get_byte_length(base) < 60:
        avail = 60 - get_byte_length(base)
        random.shuffle(FILLER_WORDS)
        for w in FILLER_WORDS:
            if get_byte_length(w) <= avail:
                base += w
                avail -= get_byte_length(w)
            else:
                break

    return {"title_cn": base, "taobao_title": base}
