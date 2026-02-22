from pathlib import Path
import psycopg2
import re
import unicodedata
from config import BARBOUR  # ✅ 使用 config 中的路径和连接配置

# === 通用关键词过滤 ===
COMMON_WORDS = {
    "jacket", "coat", "gilet", "vest", "shirt", "top",
    "t-shirt", "pants", "trousers", "shorts", "parka"
}

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str):
    style_name = normalize_text(style_name)
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    return [w for w in words if w not in COMMON_WORDS]

def parse_outdoor_txt_file(filepath: Path):
    """解析 outdoorandcountry TXT 文件，提取出所有尺码的记录"""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {"sizes": []}
    for line in lines:
        if line.startswith("Product Name:"):
            info["style_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color:"):
            info["color"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color Code:"):
            info["color_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("  "):  # Offer 行
            parts = line.strip().split("|")
            if len(parts) >= 1:
                size = parts[0].strip()
                if size:
                    info.setdefault("sizes", []).append(size)

    if "color_code" not in info or "style_name" not in info or "color" not in info or not info["sizes"]:
        print(f"⚠️ 信息不完整，跳过文件: {filepath.name}")
        return []

    keywords = extract_match_keywords(info["style_name"])
    return [
        {
            "color_code": info["color_code"],
            "style_name": info["style_name"],
            "color": info["color"],
            "size": size,
            "match_keywords": keywords
        }
        for size in info["sizes"]
    ]

def insert_into_barbour_products(records: list, conn):
    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO barbour_products (color_code, style_name, color, size, match_keywords)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (color_code, size) DO NOTHING
            """, (
                r["color_code"],
                r["style_name"],
                r["color"],
                r["size"],
                r["match_keywords"]
            ))
    conn.commit()

def batch_import_outdoor_txt():
    txt_dir = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
    conn = psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

    files = list(txt_dir.glob("*.txt"))
    total = 0

    for file in files:
        records = parse_outdoor_txt_file(file)
        if records:
            insert_into_barbour_products(records, conn)
            print(f"✅ 导入 {file.name}，共 {len(records)} 条")
            total += len(records)

    conn.close()
    print(f"\n🎉 导入完成，共导入 {total} 条记录")

if __name__ == "__main__":
    batch_import_outdoor_txt()
