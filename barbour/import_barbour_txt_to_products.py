from pathlib import Path
import psycopg2
import re
import unicodedata
from config import PGSQL_CONFIG  # ✅ 从 config 中读取连接配置
from barbour.color_utils import normalize_color

# === 通用词过滤（不纳入关键词） ===
COMMON_WORDS = {
    "jacket", "coat", "gilet", "vest", "shirt", "top",
    "t-shirt", "pants", "trousers", "shorts", "parka"
}

def normalize_text(text: str) -> str:
    # 将 Unicode 字符（如 ®、™）转换为 ASCII，丢弃无法转换的部分
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str):
    # 1. Unicode 归一化，移除所有注册商标/奇怪字符
    style_name = normalize_text(style_name)

    # 2. 移除非字母数字字符（保留空格）
    cleaned = re.sub(r"[^\w\s]", "", style_name)

    # 3. 分词并过滤通用词
    words = [w.lower() for w in cleaned.split() if len(w) >= 3]
    return [w for w in words if w not in COMMON_WORDS]

def parse_txt_file(filepath: Path):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {"sizes": []}

    for line in lines:
        if line.startswith("Product Code:"):
            info["color_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Name:"):
            info["style_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color:"):
            info["color"] = line.split(":", 1)[1].replace("-", "").strip()
        elif line.startswith("Product Size:"):
            size_part = line.split(":", 1)[1]
            info["sizes"] = [s.split(":")[0].strip() for s in size_part.split(";") if s.strip()]

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

def insert_into_products(records: list, conn):
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

def batch_import_txt(txt_dir: Path):
    conn = psycopg2.connect(**PGSQL_CONFIG)
    files = list(txt_dir.glob("*.txt"))
    total = 0

    for file in files:
        records = parse_txt_file(file)
        if records:
            insert_into_products(records, conn)
            print(f"✅ 导入 {file.name}，共 {len(records)} 条")
            total += len(records)

    conn.close()
    print(f"\n🎉 导入完成，共导入 {total} 条记录")

if __name__ == "__main__":
    txt_dir = Path(r"D:\TB\Products\barbour\publication\TXT")
    batch_import_txt(txt_dir)
