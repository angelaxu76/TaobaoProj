import re
import random
from config import BRAND_NAME_MAP
from common_taobao.core.translate import safe_translate

# =========================
# 基础映射（与现有保持一致/兼容）
# =========================
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
def get_primary_material_cn(material_en: str) -> str:
    parts = re.split(r"[ /,|]+", material_en or "")
    for part in parts:
        pc = part.strip().capitalize()
        if pc in MATERIAL_MAP:
            return MATERIAL_MAP[pc]
    return (parts[0] if parts and parts[0] else "材质未知")

def extract_field_from_content(content: str, field: str) -> str:
    pattern = re.compile(rf"{field}[:：]?\s*(.+)", re.IGNORECASE)
    m = pattern.search(content or "")
    return m.group(1).strip() if m else ""

def extract_features_from_content(content: str) -> list[str]:
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
    # 关键：GORE-TEX -> 防水
    if "gore-tex" in c or "gore tex" in c or "goretex" in c:
        features.append("防水")
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

# ======= 仅修复：英文性别残留 & 性别未映射为“男鞋/女鞋/童鞋” =======
def _strip_gender_words(s: str) -> str:
    if not s: return s
    # 去掉英文性别（包含 for women/for men、Women's/Men's 等）
    s = re.sub(r"(?i)\b(for\s+women|for\s+men|women|women['’]s|womens|men|men['’]s|mens|kid|kids|child|children)\b", "", s)
    # 再清理被删词后残留的孤立 's / ’s
    s = re.sub(r"\b['’]s\b", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()

def _normalize_gender(gender_raw: str, title_en: str) -> str:
    """标准化为：女款/男款/童款；若字段缺失，从 Product Name 猜测。"""
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

# 系列/款式抽取
_ECCO_SERIES_PAT = re.compile(r"(?i)\b(soft\s*\d+|street\s*\d+|biom\s*[a-z0-9\-]*|mx|collin|cozmo|grainer|track\s*\d+|exostride|exohike|metropole)\b")
_CAMPER_SERIES_PAT = re.compile(r"(?i)\b(junction|pelotas|runner|peu|twins|right|oruga|drift|kobarah|beetle|walden|pix|match|brutus|wabi|impar|neuman)\b")

def extract_series_from_name(brand_key: str, product_name: str) -> str:
    if not product_name: return ""
    bk = (brand_key or "").lower()
    s = product_name
    m = None
    if bk == "ecco":
        m = _ECCO_SERIES_PAT.search(s)
    elif bk == "camper":
        m = _CAMPER_SERIES_PAT.search(s)
    if not m:
        # 通用兜底：单词 + 可选数字（如 Street 720）
        m = re.search(r"(?i)\b([a-z]+(?:\s*\d+){1,2})\b", s)
    if not m: return ""
    series = re.sub(r"\s+", " ", m.group(1).strip())
    return series.title()

# 英文名兜底颜色
COLOR_GUESS = {
    "black": "黑色", "white": "白色", "off white": "米白色", "ecru": "米色",
    "brown": "棕色", "tan": "棕色", "navy": "深蓝色", "blue": "蓝色", "green": "绿色",
    "red": "红色", "beige": "米色", "grey": "灰色"
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

# =========================
# 主函数：签名保持不变（pipeline 无需修改）
# =========================
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    brand_en, brand_cn = BRAND_NAME_MAP.get((brand_key or "").lower(), (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    # 提取基础字段
    title_en     = extract_field_from_content(content, "Product Name")
    material_en  = extract_field_from_content(content, "Product Material")
    color_en     = extract_field_from_content(content, "Product Color")
    gender_raw   = extract_field_from_content(content, "Product Gender") or "女款"

    # Clarks 特殊款式提取（沿用现有行为，不影响原仓库逻辑）
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
        # 否则先用 Product Name 的首词作为系列/款式名初值（与旧行为一致）
        style_name = (title_en.split()[0].capitalize() if title_en else "系列")

    # 去除英文性别残留（Women's/Men's/for women...）
    style_name = _strip_gender_words(style_name)

    # 把系列名（如 Street 720 / Junction / Soft 7）注入到 style_name，避免丢失
    series = extract_series_from_name(brand_key, title_en or style_name or "")
    if series and series.lower() not in (style_name or "").lower():
        style_name = f"{series}{style_name}"

    # 颜色：优先用 Product Color；否则从英文标题里猜
    color_en_clean = (color_en or "").strip().lower()
    if not color_en_clean:
        title_lower = (title_en or "").lower()
        for ckw in color_keywords:
            if ckw in title_lower:
                color_en_clean = ckw; break
    color_cn = COLOR_MAP.get(color_en_clean, color_en_clean) or guess_color_cn_from_name(title_en)

    # 材质
    material_cn = get_primary_material_cn(material_en)

    # ===== 修复点：性别标准化并映射到“男鞋/女鞋/童鞋” =====
    gender_std = _normalize_gender(gender_raw, title_en)
    gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}[gender_std]

    # 特性（含 GORE-TEX -> 防水）
    features = extract_features_from_content(content + " " + (title_en or ""))
    banned = ["最", "唯一", "首个", "国家级", "世界级", "顶级"]
    features_str = "".join([f for f in features if not any(b in f for b in banned)])  # 连续拼接以节省字节

    # 鞋型
    shoe_type = determine_shoe_type(title_en, content)

    # 组装主干
    base_title = f"{brand_full}{gender_str}{style_name}{shoe_type}{color_cn}{material_cn}{features_str}".strip()
    base_title = base_title.replace("No Data", "")

    # 加入商品编码（按品牌短码规则；默认后缀）
    short_code = extract_short_code(product_code, brand_key=brand_key)
    if short_code:
        base_title = f"{base_title}{short_code}"

    # 清理异常符号重复（例如出现连续【】）
    base_title = re.sub(r"[【】]{2,}", "", base_title)

    # 严格 60 字节限制：先尝试裁掉特性词
    if get_byte_length(base_title) > 60:
        base_title = f"{brand_full}{gender_str}{style_name}{color_cn}{material_cn}".strip()
        if short_code:
            base_title = f"{base_title}{short_code}"
        if get_byte_length(base_title) > 60:
            base_title = truncate_to_max_bytes(base_title, 60)

    # 不足则用流量词补齐
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
