# generate_taobao_title_v2.py
import re
import random
from config import BRAND_NAME_MAP
from common.core.logger_utils import setup_logger
from cfg.taobao_title_keyword_config import (
    COLOR_MAP, COLOR_KEYWORDS, COLOR_GUESS,
    MATERIAL_CANON_MAP, TERM_REPLACE_MAP,
    SHOE_TYPE_MAP, FEATURE_MAP,
    FEATURE_MERGE_RULES, FEATURE_FORCE_FIRST, MAX_FEATURES,
    BRAND_SHORT_CODE_RULE, SHORT_CODE_JOIN_WITH_SPACE,
    FILLER_WORDS, MAX_SHOE_TYPES
)

logger = setup_logger(
    log_dir="d:/logs/taobao_title",
    filename="generate_taobao_title.log",
    max_mb=20,
    backup_count=10
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
    t = _norm_text(text)
    for cn, variants in keyword_map.items():
        for v in variants:
            v2 = _norm_text(v)
            if v2 and v2 in t:
                return cn
    return ""

def match_many_from_map(text: str, keyword_map: dict) -> list[str]:
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
# 短码规则
# =========================
def extract_short_code(product_code: str, brand_key: str = None, mode: str = "style") -> str:
    if not product_code:
        return ""
    s = str(product_code).strip()
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
    for cn, variants in TERM_REPLACE_MAP.items():
        for v in variants:
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
# 核心：关键词扫描（shoe_types / features / material）
# =========================
def scan_keywords(title: str, content: str) -> dict:
    text = (title or "") + " " + (content or "")

    shoe_types = match_many_from_map(text, SHOE_TYPE_MAP)[:MAX_SHOE_TYPES]
    material = match_first_from_map(text, MATERIAL_CANON_MAP)
    features = match_many_from_map(text, FEATURE_MAP)

    for needed_set, merged in FEATURE_MERGE_RULES:
        if needed_set.issubset(set(features)):
            features = [f for f in features if f not in needed_set]
            features.insert(0, merged)

    for x in reversed(FEATURE_FORCE_FIRST):
        if x in features:
            features = [x] + [f for f in features if f != x]

    features = features[:MAX_FEATURES]

    return {"shoe_types": shoe_types, "material": material, "features": features}

# =========================
# 60 字节控制 + 不足补齐（v2：把你旧版逻辑完整合回来）
# =========================
def enforce_60_bytes_title(
    title: str,
    brand_full: str,
    gender_str: str,
    style_name: str,
    shoe_type_str: str,
    color_cn: str,
    material_cn: str,
    short_code: str
) -> str:
    base_title = title.strip()
    base_title = base_title.replace("No Data", "").strip()
    base_title = re.sub(r"[【】]{2,}", "", base_title)

    # 超 60：先去掉特性，保留核心信息（跟你旧版一致思路）
    if get_byte_length(base_title) > 60:
        core_parts = [brand_full, gender_str, style_name, shoe_type_str, color_cn, material_cn]
        core = "".join([p for p in core_parts if p]).strip()
        core = _fix_english_spacing(core)
        core = _replace_terms_to_cn(core)

        if short_code:
            joiner = " " if SHORT_CODE_JOIN_WITH_SPACE else ""
            core = _fix_english_spacing(f"{core}{joiner}{short_code}")

        base_title = core

        if get_byte_length(base_title) > 60:
            base_title = truncate_to_max_bytes(base_title, 60)

    # 不足 60：补齐（保持旧行为）
    if get_byte_length(base_title) < 60:
        available = 60 - get_byte_length(base_title)
        words = FILLER_WORDS[:]   # ✅ 不修改原列表
        random.shuffle(words)
        for w in words:
            wb = get_byte_length(w)
            if available >= wb:
                base_title += w
                available -= wb
            else:
                break

    return base_title

# =========================
# 主函数
# =========================
def generate_taobao_title(product_code: str, content: str, brand_key: str) -> dict:
    try:
        logger.info(f"START | brand={brand_key} | code={product_code}")

        bk = (brand_key or "").lower()
        brand_en, brand_cn = BRAND_NAME_MAP.get(bk, (brand_key.upper(), brand_key))
        brand_full = f"{brand_en}{brand_cn}"

        title_en = extract_field_from_content(content, "Product Name")
        if not title_en:
            logger.warning(f"NO Product Name | code={product_code}")

        color_en = extract_field_from_content(content, "Product Color")
        gender_raw = extract_field_from_content(content, "Product Gender") or "女款"

        style_name = (title_en.split()[0].capitalize() if title_en else "系列")
        style_name = _strip_gender_words(style_name)

        color_en_clean = normalize_color_en(color_en)
        if not color_en_clean:
            logger.warning(f"NO Color | code={product_code}")

        color_cn = COLOR_MAP.get(color_en_clean, "") or guess_color_cn_from_name(title_en)

        gender_std = _normalize_gender(gender_raw, title_en)
        gender_str = {"女款": "女鞋", "男款": "男鞋", "童款": "童鞋"}[gender_std]

        kw = scan_keywords(title_en, content)
        shoe_types = kw.get("shoe_types") or []
        shoe_type_str = "".join(shoe_types) if shoe_types else "休闲鞋"

        material_cn = kw.get("material", "")
        features_str = "".join(kw.get("features") or [])

        parts = [brand_full, gender_str, style_name, shoe_type_str, color_cn, material_cn, features_str]
        base_title = "".join([p for p in parts if p]).strip()
        base_title = _fix_english_spacing(base_title)
        base_title = _replace_terms_to_cn(base_title)

        # 短码
        short_code = ""
        short_cfg = BRAND_SHORT_CODE_RULE.get(bk, BRAND_SHORT_CODE_RULE.get("default", {}))
        if short_cfg.get("enable"):
            short_code = extract_short_code(product_code, brand_key=bk, mode=short_cfg.get("mode", "style"))
            if short_code:
                joiner = " " if SHORT_CODE_JOIN_WITH_SPACE else ""
                base_title = f"{base_title}{joiner}{short_code}"

        # ✅ v2：严格 60 字节 + 不足补齐（补回旧逻辑）
        base_title = enforce_60_bytes_title(
            title=base_title,
            brand_full=brand_full,
            gender_str=gender_str,
            style_name=style_name,
            shoe_type_str=shoe_type_str,
            color_cn=color_cn,
            material_cn=material_cn,
            short_code=short_code
        )

        logger.info(f"OK | brand={brand_key} | code={product_code} | title={base_title}")
        return {"title_cn": base_title, "taobao_title": base_title}

    except Exception as e:
        logger.exception(f"FAILED | brand={brand_key} | code={product_code} | error={e}")
        return {"title_cn": "", "taobao_title": "", "error": str(e)}
