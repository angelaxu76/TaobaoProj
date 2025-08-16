
# -*- coding: utf-8 -*-
# 生成 Barbour 外套/夹克 的淘宝标题（服装词汇版）
# 本版加入 format_cn_title：去掉中间破折号；英文-英文保留空格；中文-中文去掉空格；中英之间保留空格。

import sys
import re
import unicodedata
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text

# ========== 读取配置（若无则使用内置默认） ==========
try:
    from config import BRAND_CONFIG
    _cfg = BRAND_CONFIG.get("barbour") or BRAND_CONFIG.get("Barbour") or {}
    PGSQL = _cfg.get("PGSQL_CONFIG") or {}
    DEFAULT_OUTPUT_DIR = (_cfg.get("OUTPUT_DIR") or Path(".")).__str__()
except Exception:
    PGSQL = {}
    DEFAULT_OUTPUT_DIR = "."

PGSQL.setdefault("host", "localhost")
PGSQL.setdefault("port", 5432)
PGSQL.setdefault("user", "postgres")
PGSQL.setdefault("password", "postgres")
PGSQL.setdefault("dbname", "postgres")

# ========== 词典与规则 ==========
SERIES_WHITELIST = {
    "ashby","bedale","beaufort","liddesdale","annandale",
    "deveron","lowerdale","border","bristol","duke","dukeley",
    "sapper","international"
}

COLOR_MAP = {
    "olive":"橄榄绿","sage":"鼠尾草绿","navy":"海军蓝","royal blue":"宝蓝",
    "black":"黑色","charcoal":"炭灰","grey":"灰色","gray":"灰色",
    "brown":"棕色","russet":"赤褐","rust":"铁锈红","red":"红色","burgundy":"酒红",
    "tan":"茶色","stone":"石色","sand":"沙色","beige":"米色","cream":"奶油色",
    "white":"白色","off white":"米白","ivory":"象牙白",
    "blue":"蓝色","light blue":"浅蓝","dark blue":"深蓝",
    "green":"绿色","forest":"墨绿","emerald":"祖母绿",
    "mustard":"芥末黄","yellow":"黄色","khaki":"卡其",
    "pale pink":"浅粉","pink":"粉色","rose":"玫瑰粉",
    "antique":"复古色","classic tartan":"经典格","tartan":"格纹",
    "empire green":"帝国绿","dark brown":"深棕","antique pine":"仿古松木色",
}

# 材质/品类识别
TYPE_RULES = [
    (r"\bwax(ed)?\b", "蜡棉"),
    (r"\bquilt(ed|ing)?\b", "绗缝"),
    (r"\bgilet|vest\b", "马甲"),
    (r"\bparka\b", "派克"),
    (r"\bparka|parka coat\b", "派克大衣"),
    (r"\bliner\b", "内胆"),
    (r"\bwaterproof|hydro|dry|proof\b", "防风防小雨"),
    (r"\bfleece\b", "抓绒"),
    (r"\bfield jacket|jacket\b", "夹克"),
    (r"\bcoat\b", "外套"),
]

# 服装热词（安全无极限词）
SAFE_HOTWORDS = ["英伦风","通勤","经典款","秋冬","百搭","耐穿","舒适版型","口碑款"]

# 违禁词（广告法极限词/夸大词，出现则删）
BANNED = [
    "最高级","最优","唯一","极致","顶级","国家级","世界级","全网最低",
    "百分之百正品","100%正品","永久","绝对","最佳","无敌","神器","镇店之宝",
]

SQL_PRODUCT = text("""
    SELECT DISTINCT color_code, style_name, color
    FROM barbour_products
    WHERE color_code = :code
    ORDER BY style_name
    LIMIT 1
""")

def normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def calc_taobao_length(title: str) -> int:

    import unicodedata
    length = 0
    for ch in title:
        if '\u4e00' <= ch <= '\u9fff' or unicodedata.east_asian_width(ch) in ('W','F'):
            length += 2
        else:
            length += 1
    return length

def _is_cjk(ch: str) -> bool:
    return '\u4e00' <= ch <= '\u9fff'

def format_cn_title(title: str) -> str:
    # 去破折号/连接号
    t = title.replace(" - ", " ").replace(" – ", " ").replace(" — ", " ").replace("-", " ")
    # 压缩空格
    t = re.sub(r"\s+", " ", t).strip()
    # 中文-中文去空格
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    # 中文-标点/标点-中文去空格
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。、“”《》：；！？」）])", "", t)
    t = re.sub(r"(?<=[（「])\s+(?=[\u4e00-\u9fff])", "", t)
    # 中英之间保留一个空格
    t = re.sub(r"(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])", " ", t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])", " ", t)
    # 再压一次
    t = re.sub(r"\s+", " ", t).strip()
    return t

def detect_series(style_name: str) -> str:
    name = (style_name or "").lower()
    for token in SERIES_WHITELIST:
        if token in name:
            return token.capitalize()
    m = re.search(r"[A-Za-z][A-Za-z\-']+", style_name or "")
    return m.group(0) if m else ""

def detect_gender(style_name: str) -> str:
    s = (style_name or "").lower()
    if "women" in s or "women's" in s or "ladies" in s or "girl" in s:
        return "女款"
    if "men" in s or "men's" in s or "boy" in s:
        return "男款"
    return ""

def detect_type(style_name: str) -> str:
    s = (style_name or "").lower()
    for pat, zh in TYPE_RULES:
        if re.search(pat, s):
            return zh
    return "夹克"

def map_color(color: str) -> str:
    c = (color or "").strip()
    cl = c.lower()
    if "/" in cl:
        cl = cl.split("/")[0].strip()
    return COLOR_MAP.get(cl, c or "")

def sanitize(text_: str) -> str:
    out = text_
    for w in BANNED:
        out = out.replace(w, "")
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out

def build_title(brand: str, series: str, typ: str, gender: str, color_zh: str, extras: list[str]) -> str:
    tokens = [brand]
    if series: tokens.append(series)
    if typ: tokens.append(typ)
    if gender: tokens.append(gender)
    if color_zh: tokens.append(color_zh)
    tokens.extend(extras)
    title = " ".join(tokens)
    title = sanitize(title)
    return title

def fit_length(title: str, min_len=58, max_len=60, protected_words=None) -> str:
    if protected_words is None:
        protected_words = []
    protected_set = set(filter(None, protected_words))
    if calc_taobao_length(title) > max_len:
        parts = title.split(" ")
        def rebuild(pp): return " ".join([p for p in pp if p])
        # 去热词
        while calc_taobao_length(title) > max_len and parts:
            if parts[-1] not in protected_set and parts[-1] in SAFE_HOTWORDS:
                parts.pop(); title = rebuild(parts)
            else:
                break
        # 去颜色
        if calc_taobao_length(title) > max_len:
            for i in range(len(parts)-1, -1, -1):
                if parts[i] not in protected_set and parts[i] in COLOR_MAP.values():
                    parts.pop(i); title = rebuild(parts); break
        # 去性别
        for g in ("女款","男款"):
            if calc_taobao_length(title) > max_len and g in parts and g not in protected_set:
                parts.remove(g); title = rebuild(parts)
        # 简化类型
        if calc_taobao_length(title) > max_len:
            for i,p in enumerate(parts):
                if p in ("派克大衣","蜡棉外套","绗缝外套"):
                    parts[i] = "外套"; title = rebuild(parts); break
                if p in ("蜡棉夹克","绗缝夹克"):
                    parts[i] = "夹克"; title = rebuild(parts); break
        # 最后仅保留前若干关键词
        if calc_taobao_length(title) > max_len:
            kept = []
            for p in parts:
                kept.append(p)
                if len(" ".join(kept)) >= 20 and len(kept) >= 2:
                    break
            title = " ".join(kept)
    elif calc_taobao_length(title) < min_len:
        for w in SAFE_HOTWORDS:
            if w not in title:
                title = (title + " " + w).strip()
            if calc_taobao_length(title) >= min_len:
                break
    return title

def generate_title_row(rec: dict) -> dict:
    code = rec.get("color_code","").upper()
    style_name = normalize_text(rec.get("style_name",""))
    color_en = normalize_text(rec.get("color",""))
    brand = "Barbour"

    series = detect_series(style_name)
    gender = detect_gender(style_name)
    typ = detect_type(style_name)
    color_zh = map_color(color_en)

    extras = []
    if typ in ("蜡棉","蜡棉夹克","外套","夹克"):
        extras += ["英伦风","通勤","秋冬"]
        if typ == "蜡棉":
            typ = "蜡棉夹克"
    elif typ in ("绗缝","绗缝夹克","马甲"):
        extras += ["轻暖","百搭","秋冬"]
        if typ == "绗缝":
            typ = "绗缝夹克"

    title = build_title(brand, series, typ, gender, color_zh, extras)
    title = fit_length(title, 58, 60, protected_words=[brand, series])
    title = sanitize(title)
    title = format_cn_title(title)

    return {
        "Product Code": code,
        "Style Name": style_name,
        "Color (EN)": color_en,
        "Color (ZH)": color_zh,
        "Series": series,
        "Type": typ,
        "Gender": gender,
        "Title (58-60 chars)": title,
        "Length": calc_taobao_length(title),
    }

def read_codes(txt_path: Path) -> list[str]:
    codes = []
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        parts = re.split(r"[,\s]+", s)
        for p in parts:
            if p:
                codes.append(p.upper())
    seen = set(); ordered = []
    for c in codes:
        if c not in seen:
            seen.add(c); ordered.append(c)
    return ordered

def main():
    if len(sys.argv) < 2:
        print("用法：python generate_barbour_taobao_title.py codes.txt [output.xlsx]")
        sys.exit(1)

    codes_file = Path(sys.argv[1])
    if not codes_file.exists():
        print(f"❌ 找不到文件：{codes_file}")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path(DEFAULT_OUTPUT_DIR) / "barbour_titles.xlsx"

    conn_url = f"postgresql+psycopg2://{PGSQL['user']}:{PGSQL['password']}@{PGSQL['host']}:{PGSQL['port']}/{PGSQL['dbname']}"
    engine = create_engine(conn_url)

    rows = []
    codes = read_codes(codes_file)
    print(f"🔎 读取到 {len(codes)} 个编码")

    with engine.begin() as con:
        for idx, code in enumerate(codes, 1):
            rec = con.execute(SQL_PRODUCT, {"code": code}).fetchone()
            if not rec:
                rows.append({
                    "Product Code": code, "Style Name": "", "Color (EN)": "",
                    "Color (ZH)": "", "Series": "", "Type": "", "Gender": "",
                    "Title (58-60 chars)": "", "Length": 0
                })
                print(f"[{idx}/{len(codes)}] {code} → 未在 barbour_products 找到记录")
                continue
            rec = dict(rec._mapping)
            result = generate_title_row(rec)
            rows.append(result)
            print(f"[{idx}/{len(codes)}] {code} → {result['Title (58-60 chars)']} [{result['Length']}字]")

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(out_path, index=False)
    print(f"✅ 导出完成：{out_path}")

def generate_taobao_title(style_name: str, color: str, code: str = "") -> str:
    """
    对外函数：输入英文标题/颜色/编码，返回中文淘宝标题
    """
    rec = {
        "style_name": style_name,
        "color": color,
        "color_code": code
    }
    row = generate_title_row(rec)
    return row["Title (58-60 chars)"]
