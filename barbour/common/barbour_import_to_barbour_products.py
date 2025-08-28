# barbour_import_to_barbour_products.py
# -*- coding: utf-8 -*-
"""
导入统一模板 TXT 到 barbour_products（兼容旧模板，已全面切换为 product_code）
- 必填：product_code, style_name, color, size, match_keywords
- 可选：title, product_description, gender, category
- 数据来源优先级：barbour官网(0) > 有编码站点(1) > 人工补码(2)
- 解析顺序：
  1) 统一模板字段（优先）：
     Product Code / Product Name / Product Color / Product Description /
     Product Gender / Style Category / Product Size / Site Name / Source URL
  2) 兼容旧模板：
     Offer List: 行（size|price|stock|can_order）
     (Product )?Sizes: 行
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import psycopg2
import re
import unicodedata
import sys

from config import PGSQL_CONFIG, BARBOUR

# —— 可选：标题生成（存在则用，不存在忽略）——
try:
    from generate_barbour_taobao_title import generate_barbour_taobao_title
except Exception:
    generate_barbour_taobao_title = None  # 没有也不影响

# -------------------- 基础工具 --------------------
COMMON_WORDS = {
    "jacket", "coat", "gilet", "vest", "shirt", "top",
    "t-shirt", "pants", "trousers", "shorts", "parka",
    "barbour", "mens", "women", "ladies", "kids"
}

# Barbour 编码识别：如 MWX0339NY91 / LWX0339OL51 / LBA0400BK111 等
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str) -> List[str]:
    style_name = normalize_text(style_name or "")
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    return [w for w in words if w not in COMMON_WORDS]

def guess_product_code_from_filename(fp: Path) -> str | None:
    """从文件名中猜测 product_code（如 MWX0339NY91.txt）。"""
    m = RE_CODE.search(fp.stem.upper())
    return m.group(0) if m else None

def validate_minimal_fields(rec: Dict) -> Tuple[bool, List[str]]:
    required = ["product_code", "style_name", "color", "size", "match_keywords"]
    missing = [k for k in required if not rec.get(k)]
    return (len(missing) == 0, missing)

# -------------------- 统一模板解析 --------------------
def _extract_field(text: str, label_re: str) -> str | None:
    """提取单行字段：如 Product Name: ... / Product Color: ..."""
    m = re.search(rf'{label_re}\s*:\s*([^\n\r]+)', text, flags=re.S)
    return m.group(1).strip() if m else None

def _extract_multiline_field(text: str, label_re: str) -> str | None:
    """提取多行字段：如 Product Description: ...（直到下一个“Word:”字段）"""
    m = re.search(rf'{label_re}\s*:\s*(.+)', text, flags=re.S)
    if not m:
        return None
    tail = m.group(1)
    parts = re.split(r'\n\s*[A-Z][A-Za-z ]+:\s*', tail, maxsplit=1)
    return parts[0].strip() if parts else None

def _parse_sizes_from_product_size_line(text: str) -> List[str]:
    """统一模板：Product Size: 34:有货;36:无货;M:有货 ..."""
    line = _extract_field(text, r'(?i)Product\s+Size')
    if not line:
        return []
    sizes = []
    for token in line.split(";"):
        token = token.strip()
        if not token:
            continue
        size = token.split(":", 1)[0].strip()
        if size and size not in sizes:
            sizes.append(size)
    return sizes

# -------------------- 旧模板兼容 --------------------
def _extract_sizes_from_offer_list_block(text: str) -> list[str]:
    """旧：Offer List: 块中解析第一列尺码（size|price|stock|can_order）"""
    sizes = []
    in_block = False
    for line in text.splitlines():
        if not in_block:
            if re.search(r'^\s*Offer\s+List\s*:\s*$', line, flags=re.I):
                in_block = True
            continue
        if not line.strip() or re.match(r'^\s*[A-Z][A-Za-z ]+:\s*', line):
            break
        m = re.match(r'^\s*([^|]+)\|', line)
        if m:
            size = m.group(1).strip()
            size = size.split(":")[0].strip()
            if size and size not in sizes:
                sizes.append(size)
    return sizes

def _extract_sizes_from_sizes_line(text: str) -> list[str]:
    """旧：(Product )?Sizes: 行；逗号/分号/斜杠分隔"""
    m = re.search(r'(?i)(?:Product\s+)?Sizes?\s*:\s*(.+)', text)
    if not m:
        return []
    raw = m.group(1)
    parts = re.split(r'[;,/|]', raw)
    sizes = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        sizes.append(p.split(":")[0].strip())
    return sizes

# -------------------- 可选字段增强 --------------------
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
    # 仅在缺失时补
    code  = rec.get("product_code") or ""
    name  = rec.get("style_name") or ""
    color = rec.get("color") or ""
    base_text = " ".join([name, rec.get("product_description") or ""])

    if not rec.get("title") and generate_barbour_taobao_title:
        try:
            info = generate_barbour_taobao_title(code, name, color) or {}
            title_cn = info.get("Title")
            if title_cn:
                rec["title"] = title_cn
        except Exception:
            pass

    if not rec.get("gender"):
        g = infer_gender(base_text)
        if g:
            rec["gender"] = g

    if not rec.get("category"):
        c = infer_category(base_text)
        if c:
            rec["category"] = c

    return rec

# -------------------- TXT 解析（统一 + 兼容） --------------------
def parse_txt_file(filepath: Path) -> List[Dict]:
    """
    输出 records（每尺码一条）：
      product_code, style_name, color, size, match_keywords,
      + 可选：title, product_description, gender, category
      + 来源：source_site, source_url, source_rank
    """
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    info: Dict = {"sizes": []}

    # Product Code
    m = re.search(r'(?i)Product\s+(?:Color\s+)?Code:\s*([A-Z0-9]+|No\s+Data|null)', text)
    code = (m.group(1).strip() if m else None)
    if code and code.lower() not in {"no data", "null"}:
        info["product_code"] = code
    else:
        info["product_code"] = guess_product_code_from_filename(filepath)

    # Product Name
    name = _extract_field(text, r'(?i)Product\s+Name')
    if name:
        info["style_name"] = name

    # Product Color
    color = _extract_field(text, r'(?i)Product\s+Colou?r')
    if color:
        val = re.sub(r'^\-+\s*', '', color).strip()
        info["color"] = val

    # Product Description（多行）
    desc = _extract_multiline_field(text, r'(?i)Product\s+Description')
    if desc:
        info["product_description"] = desc

    # Product Gender（可选）
    g = _extract_field(text, r'(?i)Product\s+Gender')
    if g:
        gl = g.lower()
        if any(k in gl for k in ["女", "women", "ladies", "woman"]):
            info["gender"] = "女款"
        elif any(k in gl for k in ["男", "men", "mens", "man"]):
            info["gender"] = "男款"
        elif any(k in gl for k in ["童", "kid", "kids", "boy", "girl"]):
            info["gender"] = "童款"

    # Style Category（可选）
    cat = _extract_field(text, r'(?i)Style\s+Category')
    if cat:
        info["category"] = cat

    # Product Size（统一模板）
    sizes = _parse_sizes_from_product_size_line(text)
    if not sizes:
        sizes = _extract_sizes_from_offer_list_block(text)
    if not sizes:
        sizes = _extract_sizes_from_sizes_line(text)
    info["sizes"] = sizes

    # 来源（用于写入 source_* 与 rank）
    source_site = _extract_field(text, r'(?i)Site\s+Name') or ""
    source_url  = _extract_field(text, r'(?i)Source\s+URL') or ""
    info["source_site"] = source_site.strip()
    info["source_url"]  = source_url.strip()
    # rank：barbour官网=0；有编码站点=1；无编码（靠人工）=2
    if (info["source_site"] or "").lower() == "barbour":
        info["source_rank"] = 0
    elif info.get("product_code"):
        info["source_rank"] = 1
    else:
        info["source_rank"] = 2

    # —— 入库必要字段校验 ——（缺失则跳过）
    if not info.get("product_code") or not info.get("style_name") or not info.get("color") or not info["sizes"]:
        miss = [k for k in ("product_code", "style_name", "color", "sizes")
                if not info.get(k) or (k == "sizes" and not info["sizes"])]
        print(f"⚠️ 跳过（信息不完整）: {filepath.name} | 缺失: {', '.join(miss)}")
        return []

    keywords = extract_match_keywords(info["style_name"])

    # —— 生成 records（每尺码一条）——
    records: List[Dict] = []
    for size in info["sizes"]:
        r = {
            "product_code": info["product_code"],
            "style_name": info["style_name"],
            "color": info["color"],
            "size": size,
            "match_keywords": keywords,
            "source_site": info.get("source_site", ""),
            "source_url": info.get("source_url", ""),
            "source_rank": info.get("source_rank", 999)
        }
        if info.get("product_description"):
            r["product_description"] = info["product_description"]
        if info.get("gender"):
            r["gender"] = info["gender"]
        if info.get("category"):
            r["category"] = info["category"]

        # 轻量 enrich（不覆盖已有值）
        r = enrich_record_optional(r)

        ok, missing = validate_minimal_fields(r)
        if not ok:
            print(f"⚠️ 跳过（行不完整）: {filepath.name} {size} | 缺失: {', '.join(missing)}")
            continue
        records.append(r)

    return records

# -------------------- DB 入库（按来源优先级保护覆盖） --------------------
def insert_into_products(records: List[Dict], conn):
    """
    UPSERT 规则：
    - 冲突键：(product_code, size)
    - 仅当 EXCLUDED.source_rank <= 现有 source_rank 时，允许覆盖基础字段
    - title：若库里为空则填
    - description/gender/category：优先新值，否则保留旧值（也受 rank 保护）
    """
    sql = """
    INSERT INTO barbour_products
      (product_code, style_name, color, size, match_keywords,
       title, product_description, gender, category,
       source_site, source_url, source_rank)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (product_code, size) DO UPDATE SET
       style_name = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.style_name ELSE barbour_products.style_name END,
       color      = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.color      ELSE barbour_products.color      END,
       -- 仅当原 title 为空时写入（避免覆盖你手工优化过的中文标题）
       title               = COALESCE(barbour_products.title, EXCLUDED.title),
       product_description = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.product_description, barbour_products.product_description) ELSE barbour_products.product_description END,
       gender              = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.gender, barbour_products.gender) ELSE barbour_products.gender END,
       category            = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN COALESCE(EXCLUDED.category, barbour_products.category) ELSE barbour_products.category END,
       source_site         = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_site ELSE barbour_products.source_site END,
       source_url          = CASE WHEN EXCLUDED.source_rank <= barbour_products.source_rank THEN EXCLUDED.source_url  ELSE barbour_products.source_url  END,
       source_rank         = LEAST(barbour_products.source_rank, EXCLUDED.source_rank);
    """
    with conn.cursor() as cur:
        for r in records:
            try:
                cur.execute(sql, (
                    r.get("product_code"),
                    r.get("style_name"),
                    r.get("color"),
                    r.get("size"),
                    r.get("match_keywords"),
                    r.get("title"),
                    r.get("product_description"),
                    r.get("gender"),
                    r.get("category"),
                    r.get("source_site"),
                    r.get("source_url"),
                    int(r.get("source_rank") or 999),
                ))
            except Exception as e:
                print(f"❌ 入库失败（记录级）: code={r.get('product_code')} size={r.get('size')} | 错误: {e}")
                conn.rollback()
                continue
    conn.commit()

# -------------------- 目录发现 & 批处理入口 --------------------
_ALIAS = {
    "oac": "outdoorandcountry",
    "outdoor": "outdoorandcountry",
    "allweather": "allweathers",
    "hof": "houseoffraser",
    "pm": "philipmorris",
}

def _discover_txt_paths_by_supplier(supplier: str = "all") -> List[Path]:
    supplier = (supplier or "all").strip().lower()
    supplier = _ALIAS.get(supplier, supplier)

    txt_dirs: Dict[str, str] = BARBOUR.get("TXT_DIRS", {}) or {}
    paths: List[Path] = []

    if supplier == "all":
        for dirpath in txt_dirs.values():
            p = Path(dirpath)
            if p.exists():
                paths.extend(sorted(p.glob("*.txt")))
        if not paths and BARBOUR.get("TXT_DIR"):
            p = Path(BARBOUR["TXT_DIR"])
            if p.exists():
                paths = sorted(p.glob("*.txt"))
        return paths

    # 指定供应商目录
    dirpath = txt_dirs.get(supplier)
    if not dirpath:
        zh_map = {"官网": "barbour", "barbour官网": "barbour", "户外": "outdoorandcountry"}
        supplier = zh_map.get(supplier, supplier)
        dirpath = txt_dirs.get(supplier)

    p = Path(dirpath) if dirpath else None
    if p and p.exists():
        return sorted(p.glob("*.txt"))
    return []

def batch_import_txt_to_barbour_product(supplier: str = "all"):
    files = _discover_txt_paths_by_supplier(supplier)
    if not files:
        print(f"⚠️ 未找到任何 TXT 文件（supplier='{supplier}'）。请检查 BARBOUR['TXT_DIRS'] 配置或目录是否存在。")
        return

    conn = psycopg2.connect(**PGSQL_CONFIG)
    total_rows = 0
    parsed_files = 0

    for file in files:
        try:
            records = parse_txt_file(file)
            if not records:
                print(f"ⓘ 跳过（无记录）: {file.name}")
                continue
            insert_into_products(records, conn)
            print(f"✅ 导入 {file.name} — {len(records)} 条")
            total_rows += len(records)
            parsed_files += 1
        except Exception as e:
            conn.rollback()
            print(f"❌ 导入失败（文件级）: {file.name} | 错误: {e}")
            continue

    conn.close()
    print(f"\n🎉 导入完成（supplier='{supplier}'）：{parsed_files} 个文件，共 {total_rows} 条记录")

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    batch_import_txt_to_barbour_product(arg)
