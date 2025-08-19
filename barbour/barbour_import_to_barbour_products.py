# barbour_import_to_barbour_products.py
# -*- coding: utf-8 -*-
"""
将 Barbour 各站点 TXT 导入 barbour_products：
- 必填：color_code, style_name, color, size, match_keywords
- 可选：title, product_description, gender, category
TXT 支持两种来源：
1) 统一格式（推荐，与官网一致）+ Offer List: size|price|stock|can_order
2) 老格式的 Sizes: ... 行
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import psycopg2
import re
import unicodedata

# 你的项目配置
from config import PGSQL_CONFIG, BARBOUR

# 可选：发布标题生成（与发品保持一致）
try:
    from generate_barbour_taobao_title import generate_barbour_taobao_title
except Exception:
    generate_barbour_taobao_title = None  # 没有也不影响主流程


# -------------------- 基础工具 --------------------
COMMON_WORDS = {
    "jacket", "coat", "gilet", "vest", "shirt", "top",
    "t-shirt", "pants", "trousers", "shorts", "parka",
    "barbour", "mens", "women", "ladies", "kids"
}

ONE_SIZE_PREFIXES = ("LHA","MHA","LLI","MLI","MWB","LWB","UBA","LWO","MWO")
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')  # 例：LWX0339NY92 / LBA0400BK111

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str) -> List[str]:
    style_name = normalize_text(style_name or "")
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    return [w for w in words if w not in COMMON_WORDS]

def guess_color_code_from_filename(fp: Path) -> str | None:
    m = RE_CODE.search(fp.stem.upper())
    return m.group(0) if m else None

def validate_minimal_fields(rec: Dict) -> Tuple[bool, List[str]]:
    """只校验原始 5 字段。"""
    required = ["color_code", "style_name", "color", "size", "match_keywords"]
    missing = [k for k in required if not rec.get(k)]
    return (len(missing) == 0, missing)


# -------------------- Offer / 尺码解析 --------------------
def _extract_sizes_from_offer_list(text: str) -> list[str]:
    """
    统一格式：从 'Offer List:' 区块解析尺码（第一列为尺码）
    行形如：S|299.00|有货|True
    """
    sizes = []
    in_block = False
    for line in text.splitlines():
        if not in_block:
            if re.search(r'^\s*Offer\s+List\s*:\s*$', line, flags=re.I):
                in_block = True
            continue
        # 空行或下一个字段标题即结束
        if not line.strip() or re.match(r'^\s*[A-Z][A-Za-z ]+:\s*', line):
            break
        m = re.match(r'^\s*([^|]+)\|', line)
        if m:
            size = m.group(1).strip()
            size = size.split(":")[0].strip()  # 兼容 "EU 40: In Stock"
            if size and size not in sizes:
                sizes.append(size)
    return sizes


# -------------------- 字段增强（可选补全） --------------------
_GENDER_PAT = [
    (r'\b(women|ladies|woman)\b', '女款'),
    (r'\b(men|mens|man)\b',       '男款'),
    (r'\b(girl|boy|kid|kids)\b',  '童款'),
]
_CATEGORY_PAT = [
    (r'quilt',             'quilted jacket'),
    (r'\bwax',             'waxed jacket'),
    (r'\bgilet\b|vest',    'gilet'),
    (r'\bparka\b',         'parka'),
    (r'\bliner\b',         'liner'),
    (r'\bfleece\b',        'fleece'),
    (r'\bshirt\b',         'shirt'),
    (r'knit|sweater',      'knitwear'),
]

def infer_gender(text: str) -> str | None:
    t = (text or "").lower()
    for pat, val in _GENDER_PAT:
        if re.search(pat, t):
            return val
    return None

def infer_category(text: str) -> str | None:
    t = (text or "").lower()
    for pat, val in _CATEGORY_PAT:
        if re.search(pat, t):
            return val
    return None

def enrich_record_optional(rec: Dict) -> Dict:
    """
    轻量补全：title/gender/category
    - 不覆盖已有值（仅在缺失时补）
    - title 使用 generate_barbour_taobao_title（若可用）
    """
    code  = rec.get("color_code") or ""
    name  = rec.get("style_name") or ""
    color = rec.get("color") or ""
    base_text = " ".join([name, rec.get("product_description") or ""])

    # title
    if not rec.get("title") and generate_barbour_taobao_title:
        try:
            info = generate_barbour_taobao_title(code, name, color) or {}
            title_cn = info.get("Title")
            if title_cn:
                rec["title"] = title_cn
        except Exception:
            pass

    # gender
    if not rec.get("gender"):
        g = infer_gender(base_text)
        if g:
            rec["gender"] = g

    # category
    if not rec.get("category"):
        c = infer_category(base_text)
        if c:
            rec["category"] = c

    return rec


# -------------------- TXT 解析（统一 + 兼容） --------------------
def parse_txt_file(filepath: Path) -> List[Dict]:
    """
    支持两类格式：
    1) 统一格式（推荐，字段与官网一致）+ Offer List
    2) 老格式（有 Sizes: 行）
    """
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    info: Dict = {"sizes": []}

    # ---- 基础字段 ----
    # Product Code / Product Color Code（都支持）
    m = re.search(r'(?i)Product\s+(?:Color\s+)?Code:\s*([A-Z0-9]+)', text)
    info["color_code"] = (m.group(1).strip() if m else None) or guess_color_code_from_filename(filepath)

    # Product Name
    m = re.search(r'(?i)Product\s+Name:\s*([^\n\r]+)', text)
    if m:
        info["style_name"] = m.group(1).strip()

    # Product Colour / Color
    m = re.search(r'(?i)Product\s+Colou?r:\s*([^\n\r]+)', text)
    if m:
        val = m.group(1).strip()
        val = re.sub(r'^\-+\s*', '', val)  # 去掉形如 "- Navy-Classic" 的前导 "-"
        info["color"] = val

    # Product Description（可选）
    m = re.search(r'(?i)Product\s+Description:\s*(.+)', text, flags=re.S)
    if m:
        desc = m.group(1).strip()
        # 只取到下一个字段标题前
        desc = re.split(r'\n\s*[A-Z][A-Za-z ]+:\s*', desc, maxsplit=1)[0].strip()
        if desc:
            info["product_description"] = desc

    # Product Gender（可选）
    m = re.search(r'(?i)Product\s+Gender:\s*([^\n\r]+)', text)
    explicit_gender = m.group(1).strip() if m else None
    if explicit_gender:
        g = explicit_gender.lower()
        if any(k in g for k in ["女", "women", "ladies", "woman"]):
            info["gender"] = "女款"
        elif any(k in g for k in ["男", "men", "mens", "man"]):
            info["gender"] = "男款"
        elif any(k in g for k in ["童", "kid", "kids", "boy", "girl"]):
            info["gender"] = "童款"

    # Category / Title（可选）
    m = re.search(r'(?i)Category:\s*([^\n\r]+)', text)
    if m:
        info["category"] = m.group(1).strip()
    m = re.search(r'(?i)Title:\s*([^\n\r]+)', text)
    if m:
        info["title"] = m.group(1).strip()

    # ---- 尺码 ----
    sizes = _extract_sizes_from_offer_list(text)
    if not sizes:
        # 兼容老格式 (Product )?Sizes?:
        m = re.search(r'(?i)(?:Product\s+)?Sizes?\s*:\s*(.+)', text)
        if m:
            raw = m.group(1)
            parts = re.split(r'[;,/|]', raw)
            sizes = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                sizes.append(p.split(":")[0].strip())
    info["sizes"] = sizes

    # 均码兜底
    if not info["sizes"]:
        code_stub = (info.get("color_code") or filepath.stem).upper()
        if code_stub.startswith(ONE_SIZE_PREFIXES):
            info["sizes"] = ["One Size"]

    # ---- 入库前校验（仅 5 必填）----
    if not info.get("color_code") or not info.get("style_name") or not info.get("color") or not info["sizes"]:
        miss = [k for k in ("color_code", "style_name", "color", "sizes")
                if not info.get(k) or (k == "sizes" and not info["sizes"])]
        print(f"⚠️ 信息不完整: {filepath.name} | 缺失: {','.join(miss)}")
        return []

    keywords = extract_match_keywords(info["style_name"])

    # ---- 生成 records（每尺码一条）----
    records: List[Dict] = []
    for size in info["sizes"]:
        r = {
            "color_code": info["color_code"],
            "style_name": info["style_name"],
            "color": info["color"],
            "size": size,
            "match_keywords": keywords,
        }
        # 可选字段（解析到了就带上）
        if info.get("product_description"):
            r["product_description"] = info["product_description"]
        if info.get("gender"):
            r["gender"] = info["gender"]
        if info.get("category"):
            r["category"] = info["category"]
        if info.get("title"):
            r["title"] = info["title"]

        # 轻量 enrich（缺的再补；不会覆盖已有值）
        r = enrich_record_optional(r)

        ok, missing = validate_minimal_fields(r)
        if not ok:
            print(f"⚠️ 信息不完整(行): {filepath.name} {size} | 缺失: {','.join(missing)}")
            continue
        records.append(r)

    return records


# -------------------- DB 入库（只填空位） --------------------
def insert_into_products(records: List[Dict], conn):
    """
    只填空位策略：
    - title：只在现有为空时写入
    - product_description：新值优先（EXCLUDED 优先），否则保留旧值
    - gender/category：同上
    """
    sql = """
    INSERT INTO barbour_products
      (color_code, style_name, color, size, match_keywords,
       title, product_description, gender, category)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (color_code, size) DO UPDATE SET
       title               = COALESCE(barbour_products.title,               EXCLUDED.title),
       product_description = COALESCE(EXCLUDED.product_description,         barbour_products.product_description),
       gender              = COALESCE(EXCLUDED.gender,                      barbour_products.gender),
       category            = COALESCE(EXCLUDED.category,                    barbour_products.category);
    """
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (
                r.get("color_code"),
                r.get("style_name"),
                r.get("color"),
                r.get("size"),
                r.get("match_keywords"),
                r.get("title"),
                r.get("product_description"),
                r.get("gender"),
                r.get("category"),
            ))
    conn.commit()


# -------------------- 批处理入口 --------------------
def batch_import_txt_to_barbour_product():
    txt_dir = Path(BARBOUR["TXT_DIR"])
    files = sorted(txt_dir.glob("*.txt"))
    if not files:
        print(f"⚠️ 目录无 TXT：{txt_dir}")
        return

    conn = psycopg2.connect(**PGSQL_CONFIG)

    total_rows = 0
    parsed_files = 0

    for file in files:
        records = parse_txt_file(file)
        if not records:
            continue
        insert_into_products(records, conn)
        print(f"✅ 导入 {file.name} — {len(records)} 条")
        total_rows += len(records)
        parsed_files += 1

    conn.close()
    print(f"\n🎉 导入完成：{parsed_files} 个文件，共 {total_rows} 条记录")

if __name__ == "__main__":
    batch_import_txt_to_barbour_product()
