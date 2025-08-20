# barbour_import_to_barbour_products.py
# -*- coding: utf-8 -*-
"""
导入统一模板 TXT 到 barbour_products（兼容旧模板）
- 必填：color_code, style_name, color, size, match_keywords
- 可选：title, product_description, gender, category
- 解析顺序：
  1) 统一模板字段（优先）：
     Product Code / Product Name / Product Color / Product Description /
     Product Gender / Style Category / Product Size
  2) 兼容旧模板：
     Offer List: 行（size|price|stock|can_order）
     (Product )?Sizes: 行
- 目录发现：
  若 config.BARBOUR 存在 TXT_DIRS，则遍历所有站点目录；否则退回 TXT_DIR
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import psycopg2
import re
import unicodedata

from config import PGSQL_CONFIG, BARBOUR

# —— 可选：标题生成（你项目里有的话会自动用，没的话跳过）——
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

# 颜色编码（color_code）识别：支持 MWX0339NY91 / LWX0339OL51 / LBA0400BK111 等
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str) -> List[str]:
    style_name = normalize_text(style_name or "")
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    return [w for w in words if w not in COMMON_WORDS]

def guess_color_code_from_filename(fp: Path) -> str | None:
    """从文件名中猜测 color_code（如 MWX0339NY91.txt）。"""
    m = RE_CODE.search(fp.stem.upper())
    return m.group(0) if m else None

def validate_minimal_fields(rec: Dict) -> Tuple[bool, List[str]]:
    required = ["color_code", "style_name", "color", "size", "match_keywords"]
    missing = [k for k in required if not rec.get(k)]
    return (len(missing) == 0, missing)

# -------------------- 统一模板解析 --------------------
def _extract_field(text: str, label_re: str) -> str | None:
    """
    提取单行字段：如 Product Name: ... / Product Color: ...
    label_re 例：r'(?i)Product\\s+Name'
    """
    m = re.search(rf'{label_re}\s*:\s*([^\n\r]+)', text, flags=re.S)
    return m.group(1).strip() if m else None

def _extract_multiline_field(text: str, label_re: str) -> str | None:
    """
    提取多行字段：如 Product Description: ...（直到下一个“TitleCase:”字段）
    """
    m = re.search(rf'{label_re}\s*:\s*(.+)', text, flags=re.S)
    if not m:
        return None
    tail = m.group(1)
    # 截断到下一段形如 “Word Word:” 的字段标题前
    parts = re.split(r'\n\s*[A-Z][A-Za-z ]+:\s*', tail, maxsplit=1)
    return parts[0].strip() if parts else None

def _parse_sizes_from_product_size_line(text: str) -> List[str]:
    """
    统一模板：Product Size: 34:有货;36:无货;M:有货 ...
    取分号前每段的第一个“冒号左侧”为尺码
    """
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

# -------------------- 旧模板兼容（你原来的逻辑） --------------------
def _extract_sizes_from_offer_list_block(text: str) -> list[str]:
    """
    旧：Offer List: 块中解析第一列尺码（size|price|stock|can_order）
    """
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
    """
    旧：(Product )?Sizes: 行；逗号/分号/斜杠分隔
    """
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

# -------------------- 可选字段增强（与旧版一致） --------------------
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
    code  = rec.get("color_code") or ""
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
      color_code, style_name, color, size, match_keywords,
      + 可选：title, product_description, gender, category
    """
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    info: Dict = {"sizes": []}

    # ---- 统一模板字段优先 ----
    # Product Code / Product Color Code
    m = re.search(r'(?i)Product\s+(?:Color\s+)?Code:\s*([A-Z0-9]+|No\s+Data|null)', text)
    code = (m.group(1).strip() if m else None)
    if code and code.lower() not in {"no data", "null"}:
        info["color_code"] = code
    else:
        # 兜底：尝试从文件名识别（Outdoor/Allweathers/官网通常OK；HoF可能没有）
        info["color_code"] = guess_color_code_from_filename(filepath)

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

    # ---- 若没有，用旧模板兜底 ----
    if not sizes:
        sizes = _extract_sizes_from_offer_list_block(text)
    if not sizes:
        sizes = _extract_sizes_from_sizes_line(text)
    info["sizes"] = sizes

    # —— 入库必要字段校验 ——（缺失则跳过）
    if not info.get("color_code") or not info.get("style_name") or not info.get("color") or not info["sizes"]:
        miss = [k for k in ("color_code", "style_name", "color", "sizes")
                if not info.get(k) or (k == "sizes" and not info["sizes"])]
        print(f"⚠️ 跳过（信息不完整）: {filepath.name} | 缺失: {', '.join(miss)}")
        return []

    keywords = extract_match_keywords(info["style_name"])

    # —— 生成 records（每尺码一条）——
    records: List[Dict] = []
    for size in info["sizes"]:
        r = {
            "color_code": info["color_code"],
            "style_name": info["style_name"],
            "color": info["color"],
            "size": size,
            "match_keywords": keywords,
        }
        # 可选
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

# -------------------- DB 入库（只填空位策略） --------------------
def insert_into_products(records: List[Dict], conn):
    """
    沿用你原来的 UPSERT 策略：
    - 存在冲突(color_code,size)时，仅在原值为空时更新 title；
      product_description / gender / category 优先用新值，否则保留旧值。
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
            try:
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
            except Exception as e:
                # 单条失败：打印出 code/size，便于定位；跳过此条，继续下一条
                print(f"❌ 入库失败（记录级）: code={r.get('color_code')} size={r.get('size')} | 错误: {e}")
                conn.rollback()  # 回滚当前失败语句
                continue
    conn.commit()


# -------------------- 目录发现 & 批处理入口 --------------------
def _discover_txt_paths() -> List[Path]:
    """
    优先使用 BARBOUR['TXT_DIRS'] 下各站点目录；否则退回 BARBOUR['TXT_DIR']。
    这样 Outdoor / Allweathers / Barbour / House of Fraser 的 TXT 都能被导入。
    """
    paths: List[Path] = []
    txt_dirs = BARBOUR.get("TXT_DIRS")
    if isinstance(txt_dirs, dict) and txt_dirs:
        for d in txt_dirs.values():
            p = Path(d)
            if p.exists():
                paths += sorted(p.glob("*.txt"))
    else:
        p = Path(BARBOUR["TXT_DIR"])
        if p.exists():
            paths = sorted(p.glob("*.txt"))
    return paths

# —— 新增/替换：按 supplier 发现 TXT 文件 ——
from pathlib import Path
from typing import List, Dict
import sys

_ALIAS = {
    "oac": "outdoorandcountry",
    "outdoor": "outdoorandcountry",
    "allweather": "allweathers",
    "hof": "houseoffraser",
    "pm": "philipmorris",
}

def _discover_txt_paths_by_supplier(supplier: str) -> List[Path]:
    """
    根据 config.BARBOUR["TXT_DIRS"] 按供应商返回 *.txt 列表。
    supplier:
      - "all"（默认）：遍历所有已配置目录
      - 具体名称：outdoorandcountry / allweathers / barbour / houseoffraser / philipmorris
      - 支持常见别名：oac/outdoor, allweather, hof, pm
    """
    supplier = (supplier or "all").strip().lower()
    supplier = _ALIAS.get(supplier, supplier)

    txt_dirs: Dict[str, Path] = BARBOUR.get("TXT_DIRS", {}) or {}
    paths: List[Path] = []

    if supplier == "all":
        # 遍历所有目录（跳过不存在的）
        for key, dirpath in txt_dirs.items():
            p = Path(dirpath)
            if p.exists():
                paths.extend(sorted(p.glob("*.txt")))
        # 若没配 TXT_DIRS，则退回单目录
        if not paths and BARBOUR.get("TXT_DIR"):
            p = Path(BARBOUR["TXT_DIR"])
            if p.exists():
                paths = sorted(p.glob("*.txt"))
        return paths

    # 指定某一供应商
    if supplier not in txt_dirs:
        # 兜底：如果传的是 "barbour官网" 这类中文，可做一次简单映射
        zh_map = {
            "官网": "barbour",
            "barbour官网": "barbour",
            "户外": "outdoorandcountry",
            "奥特莱斯": "outdoorandcountry",
        }
        supplier = zh_map.get(supplier, supplier)

    dirpath = txt_dirs.get(supplier)
    if not dirpath:
        # 再尝试 "all" 目录
        dirpath = txt_dirs.get("all")

    p = Path(dirpath) if dirpath else None
    if p and p.exists():
        return sorted(p.glob("*.txt"))

    # 全部失败：空列表
    return []


# —— 替换：批处理入口，增加 supplier 形参 ——
def batch_import_txt_to_barbour_product(supplier: str = "all"):
    """
    导入指定供应商（或全部）的 TXT 到 barbour_products。
    supplier:
      - "all"：导入所有 BARBOUR["TXT_DIRS"] 目录
      - 具体：outdoorandcountry / allweathers / barbour / houseoffraser / philipmorris（大小写不敏感）
      - 也支持别名：oac/outdoor, allweather, hof, pm
    """
    files = _discover_txt_paths_by_supplier(supplier)
    if not files:
        print(f"⚠️ 未找到任何 TXT 文件（supplier='{supplier}'）。请检查 BARBOUR['TXT_DIRS'] 配置或目录是否存在。")
        return

    # 复用你已有的 DB 连接和入库函数
    import psycopg2
    from config import PGSQL_CONFIG

    conn = psycopg2.connect(**PGSQL_CONFIG)

    total_rows = 0
    parsed_files = 0

    for file in files:
        try:
            records = parse_txt_file(file)
            if not records:
                print(f"ⓘ 跳过（无记录）: {file.name}")
                continue

            insert_into_products(records, conn)  # ⬅️ 里面会再做逐行保护
            print(f"✅ 导入 {file.name} — {len(records)} 条")
            total_rows += len(records)
            parsed_files += 1

        except Exception as e:
            # 关键：单文件失败不阻断后续；回滚再继续下一个
            conn.rollback()
            print(f"❌ 导入失败（文件级）: {file.name} | 错误: {e}")
            continue


    conn.close()
    print(f"\n🎉 导入完成（supplier='{supplier}'）：{parsed_files} 个文件，共 {total_rows} 条记录")


# —— 可选：命令行调用（不破坏原用法） ——
if __name__ == "__main__":
    # 支持：python barbour_import_to_barbour_products.py
    #      python barbour_import_to_barbour_products.py outdoorandcountry
    #      python barbour_import_to_barbour_products.py hof
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    batch_import_txt_to_barbour_product(arg)
