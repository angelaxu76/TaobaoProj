# common/title/style_extractors.py
import re

def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _strip_gender_words(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)\b(for\s+women|for\s+men|women|women['’]s|womens|men|men['’]s|mens|kid|kids|child|children)\b", "", s)
    s = re.sub(r"\b['’]s\b", "", s)
    return _norm_space(s)

# -------------------------
# Camper：第一个词就是系列名
# -------------------------
def style_camper(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"
    # Camper 的第一个词通常就是 Pelotas/Runner/Peu...
    return title_en.split()[0].capitalize()

# -------------------------
# ECCO：优先取 | 右侧，再去掉 ECCO
# -------------------------
def style_ecco(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    right = title_en.split("|", 1)[1].strip() if "|" in title_en else title_en.strip()
    right = re.sub(r"(?i)\becco\b", "", right).strip()
    right = _norm_space(right)

    # 保留最多 3 个 token（track 30 / biom 2.2 / soft 7 / move）
    toks = right.split()
    style = " ".join(toks[:3]).strip()
    return style or "系列"

# -------------------------
# GEOX：取 | 左侧，在 MAN/WOMAN 前截断
# -------------------------
def style_geox(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    left = title_en.split("|", 1)[0].strip() if "|" in title_en else title_en.strip()
    left = _norm_space(left)

    # 在性别词前截断（MAN/WOMAN...）
    m = re.search(r"\b(MAN|WOMAN|MEN|WOMEN|BOY|GIRL|KID|KIDS)\b", left, flags=re.IGNORECASE)
    if m:
        left = left[:m.start()].strip()

    # 常见 GEOX 标题开头会带材质+鞋型描述：Suede loafers / Waterproof boots
    # 轻量去掉前两个 token，把后面作为款式段
    toks = left.split()
    if len(toks) >= 3:
        left = " ".join(toks[2:]).strip()

    # 规范化 + 号
    left = re.sub(r"\s*\+\s*", " + ", left)
    left = _norm_space(left)
    return left or "系列"

# -------------------------
# Clarks：不要用第一个词，做“智能截取”
# -------------------------
def style_clarks(title_en: str, content: str) -> str:
    if not title_en:
        return "系列"

    clean = _strip_gender_words(title_en)
    toks = clean.split()

    # 遇到颜色/材质/鞋型这些就停止
    stop_words = {
        "black","brown","tan","navy","grey","gray","beige","white","blue","green","red",
        "leather","suede","nubuck","textile","synthetic",
        "boot","boots","shoe","shoes","sneaker","sneakers","loafer","loafers","sandal","sandals",
        "ankle","heel","heels"
    }

    picked = []
    for t in toks:
        if t.lower() in stop_words:
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
    "clarks_jingya": style_clarks,
}

def extract_style_name(brand_key: str, title_en: str, content: str) -> str:
    bk = (brand_key or "").lower()
    fn = STYLE_EXTRACTORS.get(bk)
    if fn:
        return fn(title_en, content) or "系列"

    # 默认兜底：用 clarks 的“智能截取”当通用规则
    return style_clarks(title_en, content) or "系列"
