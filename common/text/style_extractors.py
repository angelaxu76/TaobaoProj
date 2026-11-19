# common/text/style_extractors.py
import re

from cfg.taobao_title_keyword_config import ECCO_SERIES_CN_MAP


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def strip_trademarks(s: str) -> str:
    """去掉 ®/™/© 等商标符号（标题里不需要）。"""
    return _norm_space(re.sub(r"[®™©]", " ", s or ""))


# 长词在前，避免 "men" 先匹配导致 "Men's" 只剩 "'s"
_GENDER_WORD_RE = re.compile(
    r"(?i)(?<![\w'’])("
    r"for\s+(?:women|men|kids|unisex)"
    r"|women['’]s|men['’]s|kids['’]|kid['’]s|children['’]s"
    r"|womens|mens|women|men|unisex|kids|kid|children|child"
    r")(?![\w'’])"
)


def _strip_gender_words(s: str) -> str:
    if not s:
        return ""
    s = _GENDER_WORD_RE.sub(" ", s)
    return _norm_space(s)


def _product_color_first_word(content: str) -> str:
    m = re.search(r"Product Color[:：]?\s*(.+)", content or "", re.IGNORECASE)
    if not m:
        return ""
    toks = re.split(r"[\s/,]+", m.group(1).strip())
    return toks[0].lower() if toks and toks[0] else ""


# -------------------------
# Camper：第一个词就是系列名
# -------------------------
def style_camper(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"
    # Camper 的第一个词通常就是 Pelotas/Runner/Peu...
    return title_en.split()[0].capitalize()


# -------------------------
# ECCO：系列名 + 中文系列名（SOFT 7 柔酷）
#   标题格式：
#     "Men's ® SOFT 7 Nubuck Trainer"        （官网营销名）
#     "Soft 11 W Lace Sneaker" / "Biom 720 M Breathru"（型号名，M/W/K 表示性别）
# -------------------------
_ECCO_STOP_WORDS = {
    # 材质
    "leather", "lea", "nubuck", "suede", "textile", "mesh", "canvas", "rubber",
    "synthetic", "wool", "neoprene",
    # 功能
    "gore-tex", "gtx", "waterproof", "wp", "breathru",
    # 鞋型/品类
    "trainer", "trainers", "sneaker", "sneakers", "shoe", "shoes", "boot", "boots",
    "sandal", "sandals", "loafer", "loafers", "lace", "lace-up", "slip-on",
    "derby", "pump", "ballerina", "moc-toe", "mid-cut", "high-cut", "low-cut",
    "walking", "outdoor", "heeled", "ankle", "chelsea", "bag", "socks", "laces",
}
_ECCO_GENDER_LETTERS = {"m", "w", "k"}  # "Soft 11 W ..." / "Grainer K ..."
_ECCO_SKIP_WORDS = {"golf"}            # golf 在标题黑名单中，不占系列名位置


def ecco_series_cn(style_en: str) -> str:
    """按最长前缀匹配 ECCO 中文系列名；未配置返回空。"""
    toks = style_en.upper().split()
    for key in sorted(ECCO_SERIES_CN_MAP, key=lambda k: -len(k.split())):
        key_toks = key.upper().split()
        if toks[:len(key_toks)] == key_toks and ECCO_SERIES_CN_MAP[key]:
            return ECCO_SERIES_CN_MAP[key]
    return ""


def style_ecco(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    # 带 "|" 时取右侧（型号段），右侧为空则用左侧
    parts = [p.strip() for p in title_en.split("|")]
    raw = parts[1] if len(parts) > 1 and parts[1] else parts[0]

    s = strip_trademarks(raw)
    s = re.sub(r"(?i)\becco\b", " ", s)
    s = _strip_gender_words(s)

    picked = []
    for t in s.split():
        tl = t.lower()
        if tl in _ECCO_SKIP_WORDS:
            continue
        if tl in _ECCO_STOP_WORDS or tl in _ECCO_GENDER_LETTERS:
            break
        picked.append(t)
        if len(picked) >= 3:
            break

    style_en = " ".join(picked).upper().strip()
    if not style_en:
        return "系列"
    cn = ecco_series_cn(style_en)
    return f"{style_en} {cn}" if cn else style_en


# -------------------------
# GEOX："<描述> <系列名(大写)> <性别> <颜色> | GEOX"
#   系列名 = 性别词前面连续的大写 token，例如：
#     "Waterproof ankle boots TREKKYUP ABX JUNIOR Dark Green" → TREKKYUP
#     "Chelsea boots SPHERICA EC7 B MAN Ochre"               → SPHERICA EC7 B
# -------------------------
_GEOX_GENDER_RE = re.compile(
    r"\b(MAN|WOMAN|MEN|WOMEN|BOY|GIRL|KID|KIDS|JUNIOR|BABY|UNISEX)\b"
)
_GEOX_DROP_TOKENS = {"ABX"}  # 防水科技，标题里由 TERM_REPLACE_MAP 统一转“防水”


def _is_upper_token(t: str) -> bool:
    if t == "+":
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    return bool(letters) and letters.isupper()


def style_geox(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    left = title_en.split("|", 1)[0].strip()
    left = strip_trademarks(left)

    m = _GEOX_GENDER_RE.search(left)
    if m:
        before = left[:m.start()].split()
        picked = []
        for t in reversed(before):
            if not _is_upper_token(t):
                break
            picked.insert(0, t)
        picked = [t for t in picked if t not in _GEOX_DROP_TOKENS]
        while picked and picked[0] == "+":
            picked.pop(0)
        style = " ".join(picked)
    else:
        # 没有性别词：退回取大写 token
        style = " ".join(t for t in left.split() if _is_upper_token(t) and t not in _GEOX_DROP_TOKENS)

    style = re.sub(r"\s*\+\s*", " + ", style)
    return _norm_space(style) or "系列"


# -------------------------
# Clarks：不要用第一个词，做“智能截取”
# -------------------------
_CLARKS_STOP_WORDS = {
    # 颜色
    "black", "brown", "tan", "navy", "grey", "gray", "beige", "white", "blue", "green", "red",
    "pink", "cream", "gold", "silver", "pewter", "taupe", "sand", "stone", "khaki", "olive",
    "burgundy", "cognac", "camel", "chestnut", "mahogany", "dark", "light", "off", "natural",
    "yellow", "orange", "purple", "rose", "nude", "ivory", "bronze", "multi", "combination",
    # 材质
    "leather", "suede", "nubuck", "textile", "synthetic", "patent", "canvas", "mesh",
    "waterproof",
    # 鞋型
    "boot", "boots", "shoe", "shoes", "sneaker", "sneakers", "trainer", "trainers",
    "loafer", "loafers", "sandal", "sandals", "ankle", "heel", "heels",
}


def style_clarks(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    clean = _strip_gender_words(strip_trademarks(title_en))
    toks = clean.split()
    color_word = _product_color_first_word(content)

    picked = []
    for t in toks:
        tl = t.lower().strip(",")
        if tl in _CLARKS_STOP_WORDS or (color_word and tl == color_word):
            break
        picked.append(t)
        if len(picked) >= 3:
            break

    return " ".join(picked).strip() or "系列"


# -------------------------
# 统一入口：品牌映射 + 兜底
# -------------------------
STYLE_EXTRACTORS = {
    "camper": style_camper,
    "ecco": style_ecco,
    "geox": style_geox,
    "clarks": style_clarks,
}


def extract_style_name(brand_key: str, title_en: str, content: str) -> str:
    if (title_en or "").strip().lower() in ("", "no data"):
        return ""
    bk = (brand_key or "").lower()
    fn = STYLE_EXTRACTORS.get(bk)
    if fn:
        return fn(title_en, content) or "系列"

    # 默认兜底：用 clarks 的“智能截取”当通用规则
    return style_clarks(title_en, content) or "系列"
