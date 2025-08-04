import os
import sys
import csv
import psycopg2
from datetime import datetime
from pathlib import Path
from config import BARBOUR

# === 连接数据库 ===
def get_connection():
    return psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

# === 提取报价 TXT 内容 ===
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
        elif "|" in line and line.strip()[0].upper() in ("SMLX"):
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

# === 从 URL 提取 color_code（如 MWX0339NY91）===
def extract_color_code_from_url(url: str) -> str:
    if "-" in url:
        last_part = url.split("/")[-1].split(".")[0]
        parts = last_part.split("-")
        return parts[-1].upper()
    return "UNKNOWN"

# === 插入 offers，如果找不到产品则记录为缺失项 ===
def insert_offer(info, conn, missing_log: list):
    site = info["site"]
    offer_url = info["url"]
    style_name = info["style_name"]
    color = info["color"]
    color_code = extract_color_code_from_url(offer_url)

    for offer in info["offers"]:
        size = offer["size"]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM barbour_products WHERE color_code = %s AND size = %s
            """, (color_code, size))
            exists = cur.fetchone()

            if not exists:
                missing_log.append((color_code, size, site, style_name, color, offer_url))
                continue

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

# === 主流程 ===
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

    # 输出缺失产品到 CSV
    if missing:
        output = Path(f"missing_products_{supplier}.csv")
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["color_code", "size", "site", "style_name", "color", "offer_url"])
            writer.writerows(missing)

        print(f"\n⚠️ 有 {len(missing)} 个产品缺失于 barbour_products，已保存: {output}")

# === 命令行入口 ===
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python import_barbour_offers.py [supplier]")
    else:
        import_txt_for_supplier(sys.argv[1])
