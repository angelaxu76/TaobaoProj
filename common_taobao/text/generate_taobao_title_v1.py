# generate_taobao_title.py (v1)
import re
import random
from config import BRAND_NAME_MAP

from cfg.taobao_title_keyword_config import (
    COLOR_MAP, COLOR_KEYWORDS, COLOR_GUESS,
    MATERIAL_CANON_MAP, TERM_REPLACE_MAP,
    SHOE_TYPE_MAP, FEATURE_MAP,
    FEATURE_MERGE_RULES, FEATURE_FORCE_FIRST, MAX_FEATURES,
    BRAND_SHORT_CODE_RULE, SHORT_CODE_JOIN_WITH_SPACE,
    FILLER_WORDS,
)

# =========================
# 工具：文本归一
# =========================
def _norm_text(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _dedupe_keep_order(items):
    return list(dict.fromkeys([x for x in items if x]))

# =========================
# 从“中文: [英文同义词...]”的 map 扫描关键词
# =========================
def match_first_from_map(text: str, keyword_map: dict) -> str:
    """
    只取第一个命中（用于 shoe_type、material）
    按 dict 插入顺序决定优先级：你在 config 里写的越靠前优先级越高
    """
    t = _norm_text(text)
    for cn, variants in keyword_map.items():
        for v in variants:
            v2 = _norm_text(v)
            # 用 “in” 做包含匹配（比正则更易维护）
            if v2 and v2 in t:
                return cn
    return ""

def match_many_from_map(text: str, keyword_map: dict) -> list[str]:
    """
    多个命中（用于 features）
    """
    t = _norm_text(text)
    hits = []
    for cn, variants in keyword_map.items():
        for v in variants:
            v2 = _norm_text(v)
            if v2 and v2 in t:
                hits.append(cn)
                break
    return _dedupe_keep_order(hits)

# =========================
# 颜色：标准化 + 映射
# =========================
def normalize_color_en(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    if s in COLOR_MAP:
        return s
    m = re.match(r"(dark|light)\s+(black|brown|blue|green|grey|gray|tan|red|pink|beige)", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s

def guess_color_cn_from_name(name: str) -> str:
    s = (name or "").lower()
    for k, v in COLOR_GUESS.items():
        if k in s:
            return v
    return ""

# =========================
# 基础字段提取
# =========================
def extract_field_from_content(content: str, field: str) -> str:
    pattern = re.compile(rf"{field}[:：]?\s*(.+)", re.IGNORECASE)
    m = pattern.search(content or "")
    return m.group(1).strip() if m else ""

# =========================
# 性别
# =========================
def _normalize_gender(gender_raw: str, title_en: str) -> str:
    g = (gender_raw or "").strip().lower()
    t = (title_en or "").strip().lower()

    def _to_std(s: str) -> str:
        if not s:
            return ""
        if re.search(r"\b(women|women['’]s|female|lady|ladies)\b", s):
            return "女款"
        if re.search(r"\b(men|men['’]s|male)\b", s):
            return "男款"
        if re.search(r"\b(kid|kids|child|children|boy|girl)\b", s):
            return "童款"
        return ""

    return _to_std(g) or _to_std(t) or "女款"

def _strip_gender_words(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"(?i)\b(for\s+women|for\s+men|women|women['’]s|womens|men|men['’]s|mens|kid|kids|child|children)\b", "", s)
    s = re.sub(r"\b['’]s\b", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()

# =========================
# 短码规则（保留你原来的行为）
# =========================
def extract_short_code(product_code: str, brand_key: str = None, mode: str = "style") -> str:
    if not product_code:
        return ""
    s = str(product_code).strip()
    bk = (brand_key or "").lower()

    if mode == "ecco_6":
        return s[:6]
    if mode == "style":
        return s.split("-")[0]
    if mode == "compact":
        return re.sub(r"[^0-9A-Za-z]+", "", s)
    return s

# =========================
# 英文空格修复（可读性）
# =========================
def _fix_english_spacing(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([A-Za-z])", r"\1 \2", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

# =========================
# 英文术语替换为中文（基于 TERM_REPLACE_MAP）
# =========================
def _replace_terms_to_cn(s: str) -> str:
    if not s:
        return s

    low = s
    # 逐组替换（用“包含替换”，不写正则也好维护）
    for cn, variants in TERM_REPLACE_MAP.items():
        for v in variants:
            # 用较宽松的忽略大小写替换
            pattern = re.compile(re.escape(v), re.IGNORECASE)
            low = pattern.sub(cn, low)

    low = re.sub(r"\s{2,}", " ", low).strip()
    return low

# =========================
# 字节控制
# =========================
def get_byte_length(text: str) -> int:
    return len((text or "").encode("gbk", errors="ignore"))

def truncate_to_max_bytes(text: str, max_bytes: int) -> str:
    res, total = "", 0
    for ch in text or "":
        clen = len(ch.encode("gbk", errors="ignore"))
        if total + clen > max_bytes:
            break
        res += ch
        total += clen
    return res

# =========================
# 核心：关键词扫描（shoe_type / features / material）
# =========================
def scan_keywords(title: str, content: str) -> dict:
    text = (title or "") + " " + (content or "")

    shoe_type = match_first_from_map(text, SHOE_TYPE_MAP)
    material = match_first_from_map(text, MATERIAL_CANON_MAP)
    features = match_many_from_map(text, FEATURE_MAP)

    # 合并规则（如 加绒+保暖 → 加绒保暖）
    for needed_set, merged in FEATURE_MERGE_RULES:
        if needed_set.issubset(set(features)):
            features = [f for f in features if f not in needed_set]
            features.insert(0, merged)

    # 强制置顶（如 防水）
    for x in reversed(FEATURE_FORCE_FIRST):
        if x in features:
            features = [x] + [f for f in features if f != x]

    # 限制数量
    features = features[:MAX_FEATURES]

    return {
        "shoe_type": shoe_type,
        "material": material,
        "features": features
    }

# =========================
# 主函数：签名不变
# =========================
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    bk = (brand_key or "").lower()
    brand_en, brand_cn = BRAND_NAME_MAP.get(bk, (brand_key.upper(), brand_key))
    brand_full = f"{brand_en}{brand_cn}"

    # 1) 读基础字段
    title_en = extract_field_from_content(content, "Product Name")
    color_en = extract_field_from_content(content, "Product Color")
    gender_raw = extract_field_from_content(content, "Product Gender") or "女款"

    # 2) style_name：v1 先保持简单（第一词），避免过度复杂
    style_name = (title_en.split()[0].capitalize() if title_en else "系列")
    style_name = _strip_gender_words(style_name)

    # 3) 颜色（标准化英文→COLOR_MAP；否则从标题猜）
    color_en_clean = normalize_color_en(color_en)
    if not color_en_clean:
        tl = (title_en or "").lower()
        for ckw in COLOR_KEYWORDS:
            if ckw in tl:
                color_en_clean = ckw
                break
    color_cn = COLOR_MAP.get(color_en_clean, "") or guess_color_cn_from_name(title_en)

    # 4) 性别标准化
    gender_std = _normalize_gender(gender_raw, title_en)
    gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}[gender_std]

    # 5) 扫关键词（鞋型/材质/特性）
    kw = scan_keywords(title_en, content)
    shoe_type = kw["shoe_type"] or "休闲鞋"
    material_cn = kw["material"]  # 若扫不到就空
    features_str = "".join(kw["features"])

    # 6) 拼 parts（标题骨架）
    parts = [
        brand_full,
        gender_str,
        style_name,
        shoe_type,
        color_cn,
        material_cn,
        features_str
    ]
    base_title = "".join([p for p in parts if p]).strip()
    base_title = _fix_english_spacing(base_title)
    base_title = _replace_terms_to_cn(base_title)
    base_title = base_title.replace("No Data", "")

    # 7) 短码（按品牌开关）
    short_cfg = BRAND_SHORT_CODE_RULE.get(bk, BRAND_SHORT_CODE_RULE.get("default", {}))
    if short_cfg.get("enable"):
        short_code = extract_short_code(product_code, brand_key=bk, mode=short_cfg.get("mode", "style"))
        if short_code:
            joiner = " " if SHORT_CODE_JOIN_WITH_SPACE else ""
            base_title = f"{base_title}{joiner}{short_code}"

    # 8) 清理异常符号重复
    base_title = re.sub(r"[【】]{2,}", "", base_title)

    # 9) 60 字节控制（超长→先去特性；仍超→截断）
    if get_byte_length(base_title) > 60:
        core_parts = [brand_full, gender_str, style_name, shoe_type, color_cn, material_cn]
        core = "".join([p for p in core_parts if p]).strip()
        base_title = _fix_english_spacing(core)
        if get_byte_length(base_title) > 60:
            base_title = truncate_to_max_bytes(base_title, 60)

    # 10) 不足 60 → 补齐（v1 先沿用旧策略；后续可改成“优先补关键词”）
    if get_byte_length(base_title) < 60:
        available = 60 - get_byte_length(base_title)
        words = FILLER_WORDS[:]
        random.shuffle(words)
        for w in words:
            wb = get_byte_length(w)
            if available >= wb:
                base_title += w
                available -= wb
            else:
                break

    return {"title_cn": base_title, "taobao_title": base_title}
