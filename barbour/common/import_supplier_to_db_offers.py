import sys
import csv
import re
import unicodedata
import psycopg2
from datetime import datetime
from pathlib import Path
from config import BARBOUR
from barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS
from common_taobao.size_utils import clean_size_for_barbour  # 保留旧名

# === 通用关键词排除 ===
COMMON_WORDS = {
    "bag", "jacket", "coat", "top", "shirt",
    "backpack", "vest", "tote", "crossbody", "holdall", "briefcase"
}

# 颜色编码识别：支持 LCA0360CR11 / LQU1852BK91 / MWX0339NY91 ...
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")

def extract_match_keywords(style_name: str):
    style_name = normalize_text(style_name)
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    return [w.lower() for w in cleaned.split() if len(w) >= 3 and w.lower() not in COMMON_WORDS]

def get_connection():
    return psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])


def parse_txt(filepath: Path):
    """
    解析统一 TXT：
      - 兼容字段名：Product Code / Product Color Code；Product URL / Source URL
      - 清理 Product Color 前导 '- '
      - offer 行：size|price|stock|can_order
      - 若无 offer 行，则从 Product Size Detail / Product Size 生成
      - 若未提供 color_code，则从文件名兜底推断
    """
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

    # 额外收集，便于兜底生成
    size_line = None                # Product Size: "8:有货;10:无货;..."
    size_detail_line = None         # Product Size Detail: "8:1:EAN;10:0:EAN;..."
    price_line = None               # Product Price:
    adjusted_price_line = None      # Adjusted Price:

    for raw in lines:
        line = (raw or "").strip()

        if line.startswith("Product Name:"):
            info["style_name"] = line.split(":", 1)[1].strip()

        elif line.startswith("Product Color:"):
            val = line.split(":", 1)[1].strip()
            info["color"] = re.sub(r'^\-+\s*', '', val)

        # 兼容两种写法：Product Color Code / Product Code
        elif line.startswith("Product Color Code:") or line.startswith("Product Code:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in {"no data", "null"}:
                info["color_code"] = val

        # 兼容两种写法：Product URL / Source URL
        elif line.startswith("Product URL:") or line.startswith("Source URL:"):
            info["url"] = line.split(":", 1)[1].strip()

        elif line.startswith("Site Name:"):
            info["site"] = line.split(":", 1)[1].strip()

        elif "|" in line and line.count("|") == 3:
            # offer 行：size|price|stock|can_order
            try:
                raw_size, price, stock, avail = [x.strip() for x in line.split("|")]
                std_size = clean_size_for_barbour(raw_size)  # 识别失败会保留原样并打印⚠️
                info["offers"].append({
                    "size": std_size,
                    "price": float(str(price).replace(",", "")),
                    "stock": stock,
                    "can_order": str(avail).upper() == "TRUE"
                })
            except Exception as e:
                print(f"⚠️ Offer 行解析失败: {line} -> {e}")
                continue

        # ===== 收集兜底字段 =====
        elif line.startswith("Product Size:"):
            size_line = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size Detail:"):
            size_detail_line = line.split(":", 1)[1].strip()
        elif line.startswith("Adjusted Price:"):
            adjusted_price_line = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            price_line = line.split(":", 1)[1].strip()

    # 文件名兜底：如 LQU1852BK91.txt
    if not info["color_code"]:
        m = RE_CODE.search(filepath.stem.upper())
        if m:
            info["color_code"] = m.group(0)

    # 如果没有 offer 行，尝试从 Size Detail / Size 生成
    if not info["offers"]:
        def _parse_price(s):
            try:
                return float(str(s).strip().replace(",", ""))
            except Exception:
                return 0.0
        base_price = _parse_price(adjusted_price_line or price_line)

        # 1) 优先用 Product Size Detail: "M:1:EAN;L:0:EAN;..."
        if size_detail_line:
            for token in filter(None, [t.strip() for t in size_detail_line.split(";")]):
                parts = [p.strip() for p in token.split(":")]
                if len(parts) >= 2:
                    raw_size = parts[0]
                    stock_count = parts[1]
                    try:
                        stock_n = int(stock_count)
                    except Exception:
                        stock_n = 0
                    stock_status = "有货" if stock_n > 0 else "无货"
                    can_order = (stock_n > 0)
                    std_size = clean_size_for_barbour(raw_size)
                    info["offers"].append({
                        "size": std_size,
                        "price": base_price,
                        "stock": stock_status,
                        "can_order": can_order
                    })

        # 2) 其次用 Product Size: "S:有货;M:无货;..."
        elif size_line:
            for token in filter(None, [t.strip() for t in size_line.split(";")]):
                if ":" not in token:
                    continue
                raw_size, status = token.split(":", 1)
                status = status.strip().lower()
                stock_status = "有货" if ("有" in status or status in ("in stock", "available", "true")) else "无货"
                can_order = (stock_status == "有货")
                std_size = clean_size_for_barbour(raw_size)
                info["offers"].append({
                    "size": std_size,
                    "price": base_price,
                    "stock": stock_status,
                    "can_order": can_order
                })

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

        print(f'\n🔍 正在匹配 supplier 商品标题: "{style_name}" (颜色: {color})')
        print("关键词:", ", ".join(keywords))

        for color_code, candidate_title, match_kw in candidates:
            if not match_kw:
                continue

            match_kw_tokens = [w.lower() for w in match_kw] if isinstance(match_kw, list) else str(match_kw).lower().split()
            match_count = sum(
                1 for k in keywords
                if any(is_keyword_equivalent(k, mk) or k == mk for mk in match_kw_tokens)
            )

            print(f"🔸 候选: {color_code} ({candidate_title}), 匹配关键词数: {match_count} / {len(keywords)}")

            if match_count > best_score:
                best_match = color_code
                best_score = match_count

        required_min_score = 2
        required_min_ratio = 0.33
        actual_ratio = best_score / len(keywords) if keywords else 0

        if best_score >= required_min_score or actual_ratio >= required_min_ratio:
            print(f"✅ 匹配成功: {best_match}（匹配数: {best_score} / {len(keywords)}，比例: {actual_ratio:.0%}）\n")
            return best_match
        else:
            print(f"❌ 匹配失败：匹配数 {best_score} / {len(keywords)}，比例: {actual_ratio:.0%}，返回 None\n")
            return None


def insert_offer(info, conn, missing_log: list) -> int:
    """返回实际写入条数（0 表示没写入；<0 表示缺 color_code 等错误）"""
    site = info.get("site") or ""
    offer_url = info.get("url") or ""
    style_name = info.get("style_name") or ""
    color = info.get("color") or ""

    # 若已提供/推断 color_code，直接入库，跳过关键词匹配
    if info.get("color_code"):
        color_code = info["color_code"]
        print(f"📦 已提供/推断 color_code: {color_code} —— 直接入库，跳过关键词匹配")
    else:
        color_code = find_color_code_by_keywords(conn, style_name, color)

    if not color_code:
        for offer in info.get("offers", []):
            missing_log.append(("NO_CODE", offer.get("size"), site, style_name, color, offer_url))
        print("❗ 未匹配到 color_code，跳过本文件写入。")
        return -1

    offers = info.get("offers", [])
    if not offers:
        print("⚠️ 没有可导入的 offers（TXT 未包含 Offer List，且 Size/Detail 也未解析到）")
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for offer in offers:
            raw_size = offer.get("size")
            size = clean_size_for_barbour(raw_size)
            if not size:
                print(f"⚠️ 无法清洗尺码: {raw_size}，跳过")
                continue

            cur.execute("""
                INSERT INTO offers (color_code, size, site_name, offer_url, price_gbp, stock_status, can_order, last_checked)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (color_code, size, site_name) DO UPDATE SET
                    price_gbp=EXCLUDED.price_gbp,
                    stock_status=EXCLUDED.stock_status,
                    can_order=EXCLUDED.can_order,
                    last_checked=EXCLUDED.last_checked
            """, (
                color_code, size, site, offer_url,
                offer.get("price", 0.0), offer.get("stock", "未知"), bool(offer.get("can_order", False)), datetime.now()
            ))
            inserted += 1

    if inserted > 0:
        conn.commit()
    else:
        conn.rollback()
    return inserted


def import_txt_for_supplier(supplier: str):
    if supplier not in BARBOUR["TXT_DIRS"]:
        print(f"❌ 未找到 supplier: {supplier}")
        return

    txt_dir = BARBOUR["TXT_DIRS"][supplier]
    conn = get_connection()
    files = sorted(Path(txt_dir).glob("*.txt"))
    missing = []

    total_files = 0
    total_rows = 0

    for fpath in files:
        fname = fpath.name
        try:
            print(f"\n=== 📄 正在处理文件: {fname} ===")
            info = parse_txt(fpath)
            written = insert_offer(info, conn, missing)
            total_files += 1
            if written > 0:
                total_rows += written
                print(f"✅ 导入成功: {fname} | 写入 {written} 条 offers")
            elif written == 0:
                print(f"❗ 导入未写入数据: {fname}（无可用 offers）")
            else:
                print(f"❌ 导入失败: {fname}（未匹配 color_code）")
        except Exception as e:
            print(f"❌ 导入失败: {fname}，错误: {e}")

    conn.close()

    print(f"\n📊 汇总：处理 {total_files} 个文件，成功写入 {total_rows} 条 offers。")

    if missing:
        output = Path(f"missing_products_{supplier}.csv")
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["color_code", "size", "site", "style_name", "color", "offer_url"])
            writer.writerows(missing)
        print(f"⚠️ 有 {len(missing)} 个产品未能匹配 color_code，已记录到: {output}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python import_supplier_to_db_offers.py [supplier]")
    else:
        import_txt_for_supplier(sys.argv[1])
