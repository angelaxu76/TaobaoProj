import os
import sys
import csv
import psycopg2
from datetime import datetime
from pathlib import Path
from config import BARBOUR

COMMON_WORDS = {
    "bag", "jacket", "coat", "quilted", "top", "shirt",
    "backpack", "vest", "tote", "crossbody", "holdall", "briefcase"
}

def get_connection():
    return psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

def parse_txt(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {
        "style_name": "",
        "color": "",
        "url": "",
        "site": "",
        "offers": []
    }

    for line in lines:
        if line.startswith("Product Name:"):
            info["style_name"] = line.split("Product Name:")[1].strip()
        elif line.startswith("Product Color:"):
            info["color"] = line.split("Product Color:")[1].strip()
        elif line.startswith("Product URL:"):
            info["url"] = line.split("Product URL:")[1].strip()
        elif line.startswith("Site Name:"):
            info["site"] = line.split("Site Name:")[1].strip()
        elif "|" in line and line.strip()[0].upper() in ("SMLX1234567890"):
            try:
                size, price, stock, avail = [x.strip() for x in line.split("|")]
                info["offers"].append({
                    "size": size,
                    "price": float(price),
                    "stock": stock,
                    "can_order": avail.upper() == "TRUE"
                })
            except:
                continue
    return info

def extract_match_keywords(style_name: str):
    return [w.lower() for w in style_name.split() if len(w) >= 3 and w.lower() not in COMMON_WORDS]

def find_color_code_by_keywords(conn, style_name: str, color: str):
    keywords = extract_match_keywords(style_name)
    if not keywords:
        return None

    with conn.cursor() as cur:
        cur.execute("""
            SELECT color_code, match_keywords
            FROM barbour_products
            WHERE LOWER(color) = %s
        """, (color.lower(),))
        candidates = cur.fetchall()

        best_match = None
        best_score = 0

        for color_code, match_kw in candidates:
            if not match_kw:
                continue
            match_count = sum(1 for k in keywords if k in match_kw)
            if match_count > best_score:
                best_match = color_code
                best_score = match_count

        return best_match if best_score >= 2 else None

def insert_offer(info, conn, missing_log: list):
    site = info["site"]
    offer_url = info["url"]
    style_name = info["style_name"]
    color = info["color"]

    color_code = find_color_code_by_keywords(conn, style_name, color)

    if not color_code:
        for offer in info["offers"]:
            missing_log.append((
                "NO_CODE", offer["size"], site, style_name, color, offer_url
            ))
        return

    for offer in info["offers"]:
        size = offer["size"]

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

def import_txt_for_supplier(supplier: str):
    if supplier not in BARBOUR["TXT_DIRS"]:
        print(f"❌ 未找到 supplier: {supplier}")
        return

    txt_dir = BARBOUR["TXT_DIRS"][supplier]
    conn = get_connection()
    files = [f for f in os.listdir(txt_dir) if f.endswith(".txt")]
    missing = []

    for fname in files:
        fpath = os.path.join(txt_dir, fname)
        try:
            info = parse_txt(fpath)
            insert_offer(info, conn, missing)
            print(f"✅ 导入成功: {fname}")
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
