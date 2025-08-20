import sys
import csv
import re
import unicodedata
import psycopg2
from datetime import datetime
from pathlib import Path
from config import BARBOUR
from barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS

# === 通用关键词排除 ===
COMMON_WORDS = {
    "bag", "jacket", "coat", "top", "shirt",
    "backpack", "vest", "tote", "crossbody", "holdall", "briefcase"
}

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str):
    style_name = normalize_text(style_name)
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    return [w.lower() for w in cleaned.split() if len(w) >= 3 and w.lower() not in COMMON_WORDS]

def get_connection():
    return psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

from common_taobao.size_utils import clean_size_for_barbour  # 确保已导入

def parse_txt(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {
        "style_name": "",
        "color": "",
        "color_code": "",
        "url": "",
        "site": "",
        "offers": []
    }

    for line in lines:
        line = line.strip()
        if line.startswith("Product Name:"):
            info["style_name"] = line.split("Product Name:")[1].strip()
        elif line.startswith("Product Color:"):
            info["color"] = line.split("Product Color:")[1].strip()
        elif line.startswith("Product Color Code:"):
            info["color_code"] = line.split("Product Color Code:")[1].strip()
        elif line.startswith("Product URL:"):
            info["url"] = line.split("Product URL:")[1].strip()
        elif line.startswith("Site Name:"):
            info["site"] = line.split("Site Name:")[1].strip()
        elif "|" in line and line.count("|") == 3:
            try:
                raw_size, price, stock, avail = [x.strip() for x in line.split("|")]
                std_size = clean_size_for_barbour(raw_size)
                if std_size is None:
                    print(f"⚠️ 忽略无法识别的尺码: {raw_size}")
                    continue
                info["offers"].append({
                    "size": std_size,  # ✅ 使用清洗后的 size
                    "price": float(price),
                    "stock": stock,
                    "can_order": avail.upper() == "TRUE"
                })
            except Exception as e:
                print(f"⚠️ Offer 行解析失败: {line} -> {e}")
                continue

    return info


def is_keyword_equivalent(k1, k2):
    for group in KEYWORD_EQUIVALENTS:
        if k1 in group and k2 in group:
            return True
    return False

def find_color_code_by_keywords(conn, style_name: str, color: str):
    keywords = extract_match_keywords(style_name)
    if not keywords:
        return None

    with conn.cursor() as cur:
        cur.execute("""
            SELECT color_code, style_name, match_keywords
            FROM barbour_products
            WHERE LOWER(color) LIKE '%%' || LOWER(%s) || '%%'
        """, (color.lower(),))

        candidates = cur.fetchall()
        best_match = None
        best_score = 0

        print(f"\n🔍 正在匹配 supplier 商品标题: \"{style_name}\" (颜色: {color})")
        print("关键词:", ", ".join(keywords))

        for color_code, candidate_title, match_kw in candidates:
            if not match_kw:
                continue

            match_kw_tokens = [w.lower() for w in match_kw] if isinstance(match_kw, list) else match_kw.lower().split()
            match_count = sum(
                1 for k in keywords
                if any(is_keyword_equivalent(k, mk) or k == mk for mk in match_kw_tokens)
            )

            print(f"🔸 候选: {color_code} ({candidate_title}), 匹配关键词数: {match_count} / {len(keywords)}")

            if match_count > best_score:
                best_match = color_code
                best_score = match_count

        # ✅ 动态判断是否匹配成功
        required_min_score = 2
        required_min_ratio = 0.33
        actual_ratio = best_score / len(keywords) if keywords else 0

        if best_score >= required_min_score or actual_ratio >= required_min_ratio:
            print(f"✅ 匹配成功: {best_match}（匹配数: {best_score} / {len(keywords)}，比例: {actual_ratio:.0%}）\n")
            return best_match
        else:
            print(f"❌ 匹配失败：匹配数 {best_score} / {len(keywords)}，比例: {actual_ratio:.0%}，返回 None\n")
            return None

def insert_offer(info, conn, missing_log: list):
    site = info["site"]
    offer_url = info["url"]
    style_name = info["style_name"]
    color = info["color"]

    # ✅ 优先使用 TXT 中的 color_code，否则自动匹配
    if info.get("color_code"):
        color_code = info["color_code"]
        print(f"📦 已提供 color_code: {color_code}，跳过关键词匹配")
    else:
        color_code = find_color_code_by_keywords(conn, style_name, color)

    if not color_code:
        for offer in info["offers"]:
            missing_log.append((
                "NO_CODE", offer["size"], site, style_name, color, offer_url
            ))
        return False

    for offer in info["offers"]:
        raw_size = offer["size"]
        size = clean_size_for_barbour(raw_size)
        if not size:
            print(f"⚠️ 无法清洗尺码: {raw_size}，跳过")
            continue

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO offers (color_code, size, site_name, offer_url, price_gbp, stock_status, can_order, last_checked)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (color_code, size, site_name) DO UPDATE SET
                    price_gbp = EXCLUDED.price_gbp,
                    stock_status = EXCLUDED.stock_status,
                    can_order = EXCLUDED.can_order,
                    last_checked = EXCLUDED.last_checked
            """, (
                color_code,
                size,
                site,
                offer_url,
                offer["price"],
                offer["stock"],
                offer["can_order"],
                datetime.now()
            ))

    conn.commit()
    return True

def import_txt_for_supplier(supplier: str):
    if supplier not in BARBOUR["TXT_DIRS"]:
        print(f"❌ 未找到 supplier: {supplier}")
        return

    txt_dir = BARBOUR["TXT_DIRS"][supplier]
    conn = get_connection()
    files = sorted(Path(txt_dir).glob("*.txt"))
    missing = []

    for fpath in files:
        fname = fpath.name
        try:
            print(f"\n=== 📄 正在处理文件: {fname} ===")
            info = parse_txt(fpath)
            matched = insert_offer(info, conn, missing)
            if matched:
                print(f"✅ 导入成功: {fname}")
            else:
                print(f"❌ 导入失败: {fname}（未匹配 color_code）")
        except Exception as e:
            print(f"❌ 导入失败: {fname}，错误: {e}")

    conn.close()

    if missing:
        output = Path(f"missing_products_{supplier}.csv")
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["color_code", "size", "site", "style_name", "color", "offer_url"])
            writer.writerows(missing)

        print(f"\n⚠️ 有 {len(missing)} 个产品未能匹配 color_code，已记录到: {output}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python import_barbour_offers.py [supplier]")
    else:
        import_txt_for_supplier(sys.argv[1])
