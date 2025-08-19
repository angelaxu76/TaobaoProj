# -*- coding: utf-8 -*-
from pathlib import Path
import psycopg2
import re
import unicodedata
from typing import List, Dict, Optional

from config import PGSQL_CONFIG, BARBOUR  # ✅ 从 config 中读取连接配置
from barbour.color_utils import normalize_color

# === 通用词过滤（不纳入关键词） ===
COMMON_WORDS = {
    "jacket", "coat", "gilet", "vest", "shirt", "top", "tshirt", "t-shirt",
    "pants", "trousers", "shorts", "parka", "barbour", "mens", "women", "womens",
    "international", "bintl", "b.intl", "quilted", "puffer", "waterproof"
}

# === 基本正则 ===
RE_KV = lambda k: re.compile(rf"^{re.escape(k)}\s*:\s*(.+)$", re.I)
RE_OFFER_LINE = re.compile(r"^\s*([^\|]+)\|([\d\.]+)\|(.+?)\|(True|False)\s*$", re.I)

def normalize_text(text: str) -> str:
    """将 Unicode 字符（如 ®、™）转换为 ASCII，丢弃无法转换的部分"""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str) -> List[str]:
    # 1) Unicode 归一化
    style_name = normalize_text(style_name)
    # 2) 去符号，仅保留字母数字与空格
    cleaned = re.sub(r"[^\w\s]", " ", style_name)
    # 3) 分词、去短词、去通用词、去重
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    seen = set()
    out = []
    for w in words:
        if w in COMMON_WORDS:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out

def pick_first_color(c: str) -> str:
    """对 'Birch/Gardenia' 只保留第一个；去掉前缀 '-'；清理空白；做颜色标准化。"""
    if not c:
        return c
    # 移除前导 '-' 和多余空白
    c = c.strip()
    if c.startswith("-"):
        c = c[1:].strip()
    # 仅保留第一个斜杠之前
    c = c.split("/", 1)[0].strip()
    # 删除可能的多余连接号空格
    c = c.replace(" - ", " ").replace("-", " ").strip()
    # 颜色标准化（你项目中的词典）
    return normalize_color(c)

def infer_category(style_name: str) -> Optional[str]:
    """根据款名粗略推断分类（可替换为你现成的 category_utils）。"""
    s = style_name.lower()
    # 更具体的在前
    if "puffer" in s:
        return "Puffer Jacket"
    if "quil(t)" in s or "liddesdale" in s:
        return "Quilted Jacket"
    if "waterproof" in s or "wax" in s or "jacket" in s:
        return "Jacket"
    if "parka" in s:
        return "Parka"
    if "gilet" in s or "vest" in s:
        return "Gilet"
    if "shirt" in s:
        return "Shirt"
    if "tee" in s or "t-shirt" in s or "tshirt" in s:
        return "T-Shirt"
    return None

def infer_gender(gender_line: Optional[str], style_name: str) -> Optional[str]:
    """优先取 TXT 的 Product Gender；否则从款名猜测。"""
    if gender_line:
        g = gender_line.strip()
        if g in ("男款", "女款", "童款"):
            return {"男款": "Men", "女款": "Women", "童款": "Kids"}[g]
        # 其它情况直接回写原值（保险）
        return g
    s = style_name.lower()
    if any(k in s for k in ["women", "womens", "ladies", "l\/s women"]):
        return "Women"
    if any(k in s for k in ["men", "mens"]):
        return "Men"
    return None

def build_title(style_name: str, color_std: str) -> str:
    """生成完整标题：Barbour {style_name} – {color}"""
    # 统一破折号
    return f"Barbour {style_name} – {color_std}".strip()

def parse_sizes(lines: List[str]) -> List[str]:
    """优先解析 Offer List 下的尺码；若没有，则回退 Product Size 行。"""
    sizes = []

    # 优先：Offer List
    offer_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("offer list"):
            offer_idx = i
            break
    if offer_idx is not None:
        i = offer_idx + 1
        while i < len(lines) and lines[i].strip():
            m = RE_OFFER_LINE.match(lines[i])
            if m:
                size = m.group(1).strip()
                sizes.append(size)
            i += 1

    # 回退：Product Size
    if not sizes:
        for line in lines:
            m = RE_KV("Product Size")(line)
            if m:
                size_part = m.group(1)
                for s in size_part.split(";"):
                    s = s.strip()
                    if not s:
                        continue
                    # 支持 "M:有货" 或 "M" 两种
                    sizes.append(s.split(":")[0].strip())
                break

    # 去重、保序
    seen = set()
    ordered = []
    for s in sizes:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered

def parse_txt_file(filepath: Path) -> List[Dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info: Dict[str, Optional[str]] = {
        "color_code": None,
        "style_name": None,
        "color": None,
        "gender_line": None,
        "product_description": None,
    }

    for line in lines:
        m = RE_KV("Product Code")(line)
        if m:
            info["color_code"] = m.group(1).strip()
            continue
        m = RE_KV("Product Name")(line)
        if m:
            info["style_name"] = m.group(1).strip()
            continue
        m = RE_KV("Product Color")(line)
        if m:
            info["color"] = m.group(1).strip()
            continue
        m = RE_KV("Product Gender")(line)
        if m:
            info["gender_line"] = m.group(1).strip()
            continue
        m = RE_KV("Product Description")(line)
        if m:
            info["product_description"] = m.group(1).strip()
            continue

    sizes = parse_sizes(lines)

    if not (info["color_code"] and info["style_name"] and info["color"] and sizes):
        print(f"⚠️ 信息不完整，跳过文件: {filepath.name}")
        return []

    # 颜色标准化（含去 '-' 与斜杠后截断）
    color_std = pick_first_color(info["color"] or "")
    # 性别推断
    gender_norm = infer_gender(info.get("gender_line"), info["style_name"])
    # 类目推断
    category = infer_category(info["style_name"] or "")
    # 标题
    title = build_title(info["style_name"], color_std)
    # 匹配关键词
    keywords = extract_match_keywords(info["style_name"] or "")

    records = []
    for size in sizes:
        records.append({
            "color_code": info["color_code"],
            "style_name": info["style_name"],
            "color": color_std,
            "size": size.strip(),
            "gender": gender_norm,
            "category": category,
            "title": title,
            "product_description": info.get("product_description"),
            "match_keywords": keywords,
        })
    return records

def upsert_into_products(records: List[Dict], conn):
    """
    INSERT ... ON CONFLICT (color_code, size) DO UPDATE
    - 冲突时更新：style_name, color, gender, category, title, product_description, match_keywords
    - 利用表上的 updated_at 触发器自动更新时间戳
    """
    sql = """
    INSERT INTO barbour_products
        (color_code, style_name, color, size, gender, category, title, product_description, match_keywords)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (color_code, size) DO UPDATE SET
        style_name = EXCLUDED.style_name,
        color = EXCLUDED.color,
        gender = COALESCE(EXCLUDED.gender, barbour_products.gender),
        category = COALESCE(EXCLUDED.category, barbour_products.category),
        title = EXCLUDED.title,
        product_description = COALESCE(EXCLUDED.product_description, barbour_products.product_description),
        match_keywords = EXCLUDED.match_keywords
    """
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (
                r["color_code"], r["style_name"], r["color"], r["size"],
                r["gender"], r["category"], r["title"], r["product_description"],
                r["match_keywords"]
            ))
    conn.commit()

def batch_import_txt_to_barbour_product(txt_root: Optional[Path] = None):
    # 兼容你项目里多目录配置；若未提供，优先 TXT_DIR，再退回 TXT_DIRS/TXT_DIR_ALL
    if txt_root is None:
        txt_root = Path(BARBOUR.get("TXT_DIR") or BARBOUR.get("TXT_DIR_ALL") or BARBOUR["TXT_DIRS"][0])

    # 支持递归读取
    files = list(txt_root.rglob("*.txt")) if txt_root.is_dir() else [txt_root]
    if not files:
        print(f"⚠️ 未找到 TXT 文件：{txt_root}")
        return

    conn = psycopg2.connect(**PGSQL_CONFIG)
    total = 0
    for file in files:
        recs = parse_txt_file(file)
        if recs:
            upsert_into_products(recs, conn)
            print(f"✅ 导入 {file.name}：{len(recs)} 条")
            total += len(recs)
    conn.close()
    print(f"\n🎉 导入完成，共导入/更新 {total} 条记录")

if __name__ == "__main__":
    # 若你要直接导入刚上传的示例，可传入文件路径：
    # batch_import_txt_to_barbour_product(Path(r"/mnt/data/MWB1132NY71.txt"))
    # 否则默认用 config 中的 TXT 目录
    batch_import_txt_to_barbour_product()
