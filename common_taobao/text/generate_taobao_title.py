import re
import random
from config import BRAND_NAME_MAP
from common_taobao.core.translate import safe_translate

# =========================
# 基础映射（与现有保持一致/兼容）
# =========================
COLOR_MAP = {
    "black": "黑色", "white": "白色", "red": "红色", "navy": "深蓝色", "tan": "浅棕色",
    "brown": "棕色", "blue": "蓝色", "grey": "灰色", "gray": "灰色", "green": "绿色", "olive": "橄榄绿",
    "pink": "粉色", "burgundy": "酒红色", "beige": "米色", "cream": "奶油色",
    "silver": "银色", "gold": "金色", "stone": "石灰色", "orange": "橙色",
    "plum": "梅子色", "taupe": "灰褐色", "cola": "可乐色", "off white": "米白色",
    "pewter": "锡色", "rust": "铁锈红", "light tan": "浅棕褐", "dark tan": "深棕褐",
    # —— 新增更常见色名与组合 —— #
    "dark brown": "深棕色", "mid brown": "中棕色", "light brown": "浅棕色",
    "dark blue": "深蓝色", "light blue": "浅蓝色", "sky blue": "天蓝色", "denim": "牛仔蓝",
    "charcoal": "炭灰色", "khaki": "卡其色", "camel": "驼色", "sand": "沙色", "cognac": "干邑棕",
    "ivory": "象牙白", "cream white": "奶油白", "off-white": "米白色", "multicolor": "多色", "multi": "多色"
}
color_keywords = [
    "black", "tan", "navy", "brown", "white", "grey", "gray", "off white", "blue",
    "silver", "olive", "cream", "red", "green", "beige", "cola", "pink",
    "burgundy", "taupe", "stone", "bronze", "orange", "walnut", "pewter",
    "plum", "yellow", "rust", "khaki", "camel", "charcoal", "cognac", "sand", "multi"
]

MATERIAL_MAP = {
    "Calfskin": "小牛皮", "Leather": "牛皮", "Nubuck": "磨砂皮", "Textile": "织物",
    "Suede": "反毛皮", "Canvas": "帆布", "Mesh": "网布", "Synthetic": "合成材质",
    "Full-Grain": "头层牛皮", "Full Grain": "头层牛皮", "Patent": "漆皮", "Faux Leather": "仿皮"
}

# —— 新增：英文术语→中文通用词（材料/功能类） —— #
# 先配“长词在前”的顺序，避免 water → waterproof 被截断
TERM_MAP = [
    (r"water\s*resistant", "防泼水"),
    (r"waterproof",        "防水"),
    (r"gore[-\s]*tex",     "防水"),
    (r"full\s*[-\s]*grain", "头层牛皮"),
    (r"genuine\s*leather", "真皮"),
    (r"patent\s*leather",  "漆皮"),
    (r"leather",           "牛皮"),
    (r"nubuck",            "磨砂皮"),
    (r"suede",             "反毛皮"),
    (r"textile",           "织物"),
    (r"mesh",              "网布"),
    (r"canvas",            "帆布"),
    (r"synthetic",         "合成材质"),
]


# =========================
# 品牌短码提取规则（保持既有行为）
# =========================
def code_rule_ecco(code: str) -> str:
    return str(code).strip()[:6] if code else ""  # 前6位
def code_rule_camper(code: str) -> str:
    return str(code).strip().split("-")[0] if code else ""  # '-' 前
def code_rule_default(code: str) -> str:
    return str(code).strip() if code else ""
BRAND_CODE_RULES = {"ecco": code_rule_ecco, "camper": code_rule_camper}

def extract_short_code(product_code: str, brand_key: str = None, mode: str = "style") -> str:
    if not product_code:
        return ""
    s = str(product_code).strip()
    brand_key = (brand_key or "").lower()
    if brand_key in BRAND_CODE_RULES:
        return BRAND_CODE_RULES[brand_key](s)
    if mode == "style":
        return s.split("-")[0]
    if mode == "compact":
        return re.sub(r"[^0-9A-Za-z]+", "", s)
    return s  # full

# =========================
# 工具函数
# =========================
def normalize_color_en(raw: str) -> str:
    """新增：把 'Dark Brown'、'Light Blue'、'Off-White' 等标准化为 COLOR_MAP 键"""
    s = (raw or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    # 常见修饰词归一
    s = s.replace("dark ", "dark ").replace("light ", "light ")
    # 直接命中
    if s in COLOR_MAP:
        return s
    # 组合处理（dark/light + 基色）
    m = re.match(r"(dark|light)\s+(black|brown|blue|green|grey|gray|tan|red|pink|beige)", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s

def get_primary_material_cn(material_en: str) -> str:
    """
    输入英文材质描述，比如:
        "Premium nubuck leather upper with waterproof Gore-Tex membrane"
    返回主材质的中文，比如:
        "牛皮" / "反毛皮" / "防水" / "头层牛皮"
    规则：
    1. 优先用 MATERIAL_MAP 的精确材质词
    2. 再用 TERM_MAP 的正则特征词（防水/真皮/织物等）
    3. 如果还是没有，返回 "" 而不是 "材质未知"
    """
    parts = re.split(r"[ /,|]+", material_en or "")

    # 1. 优先用 MATERIAL_MAP（精确英文 -> 中文）
    for part in parts:
        pc = part.strip().capitalize()
        if pc in MATERIAL_MAP:
            return MATERIAL_MAP[pc]

    # 2. TERM_MAP 是 [(pattern, "中文"), ...]
    low_full = (material_en or "").lower()
    for pat, cn in TERM_MAP:
        if re.search(pat, low_full, flags=re.IGNORECASE):
            return cn

    # 3. 兜底：现在不再返回"材质未知"，而是返回空字符串
    return ""


def extract_field_from_content(content: str, field: str) -> str:
    pattern = re.compile(rf"{field}[:：]?\s*(.+)", re.IGNORECASE)
    m = pattern.search(content or "")
    return m.group(1).strip() if m else ""

def extract_features_from_content(content: str) -> list[str]:
    """改进：默认也识别 waterproof / breathable 等"""
    features = []
    c = (content or "").lower()
    if "eva" in c: features.append("EVA大底")
    if "light" in c: features.append("轻盈缓震")
    if "extra height" in c or "3cm" in c: features.append("增高")
    if "sneaker" in c or "runner" in c: features.append("复古慢跑鞋")
    if "recycled" in c: features.append("环保材质")
    if "rubber" in c: features.append("防滑橡胶底")
    if "ballet" in c: features.append("芭蕾风")
    if "removable" in c: features.append("可拆鞋垫")
    # GORE-TEX / Waterproof → 防水（新增 waterproof）
    if "gore-tex" in c or "gore tex" in c or "goretex" in c or "waterproof" in c:
        features.append("防水")
    if "breathable" in c:
        features.append("透气")
    # 去重并保持顺序
    return list(dict.fromkeys(features))

def determine_shoe_type(title: str, content: str) -> str:
    t = (title or "").lower(); c = (content or "").lower()
    if any(k in t or k in c for k in ["boot", "chelsea", "ankle"]):
        return "短靴"
    if any(k in t or k in c for k in ["sandal", "slide", "slipper", "mule", "flip-flop"]):
        return "凉鞋"
    return "休闲鞋"

def get_byte_length(text: str) -> int:
    return len((text or "").encode("gbk", errors="ignore"))

def truncate_to_max_bytes(text: str, max_bytes: int) -> str:
    res, total = "", 0
    for ch in text or "":
        clen = len(ch.encode("gbk", errors="ignore"))
        if total + clen > max_bytes: break
        res += ch; total += clen
    return res

# ======= 仅修复：英文性别残留 & 性别未映射为“男鞋/女鞋/童鞋” =======  :contentReference[oaicite:0]{index=0}
def _strip_gender_words(s: str) -> str:
    if not s: return s
    s = re.sub(r"(?i)\b(for\s+women|for\s+men|women|women['’]s|womens|men|men['’]s|mens|kid|kids|child|children)\b", "", s)
    s = re.sub(r"\b['’]s\b", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()

def _normalize_gender(gender_raw: str, title_en: str) -> str:
    g = (gender_raw or "").strip().lower()
    t = (title_en or "").strip().lower()
    def _to_std(s: str) -> str:
        if not s: return ""
        if re.search(r"\b(women|women['’]s|female|lady|ladies)\b", s): return "女款"
        if re.search(r"\b(men|men['’]s|male)\b", s):                 return "男款"
        if re.search(r"\b(kid|kids|child|children|boy|girl)\b", s):  return "童款"
        return ""
    std = _to_std(g) or _to_std(t) or "女款"
    return std

# 系列/款式抽取（保持你原有逻辑并补充 GEOX）
_ECCO_SERIES_PAT = re.compile(r"(?i)\b(soft\s*\d+|street\s*\d+|biom\s*[a-z0-9\-]*|mx|collin|cozmo|grainer|track\s*\d+|exostride|exohike|metropole)\b")
_CAMPER_SERIES_PAT = re.compile(r"(?i)\b(junction|pelotas|runner|peu|twins|right|oruga|drift|kobarah|beetle|walden|pix|match|brutus|wabi|impar|neuman)\b")
_GEOX_SERIES_PAT = re.compile(
    r"(?i)\b("
    r"aerantis|spherica|respira|nebula|blomiee|felicity|casey|annytah|fast|felleny|"
    r"brandolf|brayden|ciberdron|calithe|diamanta|eclair|elver|catria|amabel|arzach|"
    r"alnoire|eleana|agata|baltmoore|buzzerlight|federico|tivoli|walk pleasure|club|dolomia|symbol"
    r")\b"
)

def extract_series_from_name(brand_key: str, product_name: str) -> str:
    if not product_name: return ""
    bk = (brand_key or "").lower()
    s = product_name
    m = None
    if bk == "ecco":
        m = _ECCO_SERIES_PAT.search(s)
    elif bk == "camper":
        m = _CAMPER_SERIES_PAT.search(s)
    elif bk == "geox":
        m = _GEOX_SERIES_PAT.search(s)
    if not m:
        m = re.search(r"(?i)\b([a-z]+(?:\s*\d+){1,2})\b", s)
    if not m: return ""
    series = re.sub(r"\s+", " ", m.group(1).strip())
    return series.title()

COLOR_GUESS = {
    "black": "黑色", "white": "白色", "off white": "米白色", "ecru": "米色",
    "brown": "棕色", "tan": "棕色", "navy": "深蓝色", "blue": "蓝色", "green": "绿色",
    "red": "红色", "beige": "米色", "grey": "灰色", "gray": "灰色", "charcoal": "炭灰色",
    "khaki": "卡其色", "camel": "驼色", "cognac": "干邑棕", "sand": "沙色"
}
def guess_color_cn_from_name(name: str) -> str:
    s = (name or "").lower()
    for k, v in COLOR_GUESS.items():
        if k in s:
            return v
    return ""

# 流量词（与旧版保持一致）
FILLER_WORDS = [
    "新款", "百搭", "舒适", "潮流", "轻奢", "经典", "时尚", "复古",
    "透气", "柔软", "减震", "轻盈", "耐穿", "通勤", "日常", "不磨脚",
    "支撑感强", "贴合脚型", "不累脚", "细腻", "驾车", "休闲", "逛街", "出街", "回购", "简约", "英伦"
]

# ======= GEOX 专用增强（保留） =======
def _extract_features_geox(content: str) -> list[str]:
    c = (content or "").lower()
    mapping = {
        "waterproof": "防水", "gore-tex": "防水", "gore tex": "防水", "goretex": "防水",
        "breathable": "透气",
        "insulated": "保暖",
        "memory foam": "记忆海绵",
        "lightweight": "轻盈",
        "soft": "柔软舒适",
        "zip": "拉链设计", "zipped": "拉链设计",
        "lace-up": "系带设计", "velcro": "魔术贴", "buckle": "搭扣设计",
        "slip-on": "一脚蹬", "elastic": "弹力设计", "stretch": "弹力设计",
        "platform": "厚底增高", "rubber": "防滑橡胶底", "eva": "EVA大底",
        "recycled": "环保材质", "suede": "反毛皮材质", "lined": "加绒保暖", "fur": "加绒保暖",
        "warm": "加绒保暖",
    }
    features = []
    for k, v in mapping.items():
        if k in c:
            features.append(v)
    return list(dict.fromkeys(features))

def _determine_shoe_type_geox(title: str, content: str) -> str:
    t = (title or "").lower()
    c = (content or "").lower()
    if any(k in t or k in c for k in ["boot", "chelsea", "ankle"]):
        return "短靴"
    if any(k in t or k in c for k in ["sandal", "slide", "slipper", "mule", "flip-flop"]):
        return "凉鞋拖鞋"
    if any(k in t or k in c for k in ["loafer", "moccasin"]):
        return "乐福鞋"
    if any(k in t or k in c for k in ["pump", "heel", "wedge", "court shoe"]):
        return "高跟鞋"
    if any(k in t or k in c for k in ["trainer", "sneaker", "runner", "sport"]):
        return "运动鞋"
    if "ballet" in t or "ballet" in c:
        return "芭蕾鞋"
    if "platform" in t or "platform" in c:
        return "厚底鞋"
    return "休闲鞋"

# —— 新增：中英边界与英文内部空格修复 —— #
def _fix_english_spacing(s: str) -> str:
    if not s: return s
    # 在“中文-英文/数字”与“英文/数字-中文”边界加空格
    s = re.sub(r'([\u4e00-\u9fff])([A-Za-z0-9])', r'\1 \2', s)
    s = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', s)
    # 把英文块内部连接词/数字与字母之间保证一个空格（防止 Soft7 → Soft 7）
    s = re.sub(r'([A-Za-z])(\d)', r'\1 \2', s)
    s = re.sub(r'(\d)([A-Za-z])', r'\1 \2', s)
    # 多空格合并
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s

# —— 新增：把材料/功能英文残留替换为中文（避免 Leather/Waterproof 出现在中文标题里） —— #


def _replace_terms_to_cn(s: str) -> str:
    """
    用标准 re 实现大小写无关、完整词替换，
    彻底清理 Leather / Suede / Waterproof 等英文残留。
    """
    if not s:
        return s

    # 先逐项替换（词边界 + 忽略大小写）
    for pat, cn in TERM_MAP:
        s = re.sub(rf"(?i)(?<![A-Za-z0-9]){pat}(?![A-Za-z0-9])", cn, s)

    # 把 “系列 + 功能词” 重排成中文（Spherica Waterproof → Spherica 防水）
    s = re.sub(r"(?i)([A-Za-z0-9\s\-]+)\s+防水", r"\1 防水", s)
    s = re.sub(r"(?i)([A-Za-z0-9\s\-]+)\s+防泼水", r"\1 防泼水", s)

    # 清理多余空格
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s



# =========================
# 主函数：签名保持不变
# =========================
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get((brand_key or "").lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    # 提取基础字段
    title_en     = extract_field_from_content(content, "Product Name")
    material_en  = extract_field_from_content(content, "Product Material")
    color_en     = extract_field_from_content(content, "Product Color")
    gender_raw   = extract_field_from_content(content, "Product Gender") or "女款"

    # Clarks 特殊款式提取（沿用现有行为）  :contentReference[oaicite:1]{index=1}
    style_name = ""
    if (brand_key or "").lower().startswith("clarks") and title_en:
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
        style_name = (title_en.split()[0].capitalize() if title_en else "系列")
    style_name = _strip_gender_words(style_name)

    # 系列名补强（保持）
    series = extract_series_from_name(brand_key, title_en or style_name or "")
    if series and series.lower() not in (style_name or "").lower():
        style_name = f"{series} {style_name}".strip()

    # 颜色：标准化英文 → 映射中文；再兜底
    color_en_clean = normalize_color_en(color_en)
    if not color_en_clean:
        tl = (title_en or "").lower()
        for ckw in color_keywords:
            if ckw in tl:
                color_en_clean = ckw; break
    color_cn = COLOR_MAP.get(color_en_clean, "") or guess_color_cn_from_name(title_en)

    # 材质（中文）
    material_cn = get_primary_material_cn(material_en)

    # 性别标准化
    gender_std = _normalize_gender(gender_raw, title_en)
    gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}[gender_std]

    # 特性（默认也识别 waterproof；GEOX 用增强版）
    if (brand_key or "").lower() == "geox":
        features = _extract_features_geox(content + " " + (title_en or ""))
    else:
        features = extract_features_from_content(content + " " + (title_en or ""))
    banned = ["最", "唯一", "首个", "国家级", "世界级", "顶级"]
    features_str = "".join([f for f in features if not any(b in f for b in banned)])

    # 鞋型
    if (brand_key or "").lower() == "geox":
        shoe_type = _determine_shoe_type_geox(title_en, content)
    else:
        shoe_type = determine_shoe_type(title_en, content)

    # 组装（保持你原顺序，但做可读性优化）
    parts = [
        brand_full,
        gender_str,
        style_name,
        shoe_type,
        color_cn,
        material_cn,
        features_str
    ]
   # 组好 parts 后
    base_title = "".join([p for p in parts if p]).strip()

    # 1) 先做中英边界与字母/数字间空格
    base_title = _fix_english_spacing(base_title)

    # 2) 再把 Leather / Suede / Waterproof 等转中文（大小写无关 + 词边界）
    base_title = _replace_terms_to_cn(base_title)

    # 3) 清理脏值
    base_title = base_title.replace("No Data", "")

    # 加入商品短码
    short_code = ""
    if (brand_key or "").lower() in ["camper", "clarks_jingya", "ecco"]:
        short_code = extract_short_code(product_code, brand_key=brand_key)
        if short_code:
            base_title = f"{base_title} {short_code}"


    # 清理异常符号重复
    base_title = re.sub(r"[【】]{2,}", "", base_title)

    # 严格 60 字节限制（先去掉特性）
    if get_byte_length(base_title) > 60:
        core = "".join([p for p in [brand_full, gender_str, style_name, color_cn, material_cn] if p])
        base_title = _fix_english_spacing(core)
        if short_code:
            base_title = _fix_english_spacing(f"{base_title} {short_code}")
        if get_byte_length(base_title) > 60:
            base_title = truncate_to_max_bytes(base_title, 60)

    # 不足 60 则用流量词补齐（保持旧行为）
    if get_byte_length(base_title) < 60:
        available = 60 - get_byte_length(base_title)
        random.shuffle(FILLER_WORDS)
        for w in FILLER_WORDS:
            wb = get_byte_length(w)
            if available >= wb:
                base_title += w; available -= wb
            else:
                break

    return {"title_cn": base_title, "taobao_title": base_title}
