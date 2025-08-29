# import_supplier_to_db_offers.py  — 仅保留数字库存 stock_count（可覆盖）
import sys
import csv
import re
import unicodedata
import psycopg2
from datetime import datetime
from pathlib import Path
from config import BARBOUR
from barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS
from common_taobao.size_utils import clean_size_for_barbour  # 旧名保留

# ---------- 小工具 ----------
_PRICE_NUM = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')

def _parse_price(text):
    if not text:
        return None
    m = _PRICE_NUM.search(str(text).replace(",", ""))
    return float(m.group(1)) if m else None

def _to_stock_count(stock_text, can_order_text=None, default_has_stock=3):
    """
    把各种库存表示统一成数字：
    - 数字字符串：直接取 int
    - “有货/available/in stock/true”：default_has_stock（默认 3）
    - 其他：0
    """
    s = (stock_text or "").strip()
    # 1) 纯数字
    if re.fullmatch(r"\d+", s):
        try:
            return max(0, int(s))
        except Exception:
            return 0

    sl = s.lower()
    if sl in ("有货", "in stock", "instock", "available", "true", "yes"):
        return default_has_stock

    # 兼容 can_order 列
    if can_order_text is not None:
        av = str(can_order_text).strip().lower()
        if av in ("true", "1", "t", "yes", "y"):
            return default_has_stock

    return 0

def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")

COMMON_WORDS = {
    "bag", "jacket", "coat", "top", "shirt",
    "backpack", "vest", "tote", "crossbody", "holdall", "briefcase"
}

def extract_match_keywords(style_name: str):
    style_name = normalize_text(style_name)
    cleaned = re.sub(r"[^\w\s]", "", style_name)
    return [w.lower() for w in cleaned.split() if len(w) >= 3 and w.lower() not in COMMON_WORDS]

def get_connection():
    return psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])

# ---------- TXT 解析 ----------
def parse_txt(filepath: Path):
    """
    解析统一 TXT，目标是产出：
      info = {
        "style_name": "", "color": "", "product_code": "", "url": "", "site": "",
        "price_line": "...", "adjusted_price_line": "...",
        "offers": [ { "size": "UK 10", "price": 199.0, "stock_count": 3 }, ... ]
      }
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {
        "style_name": "",
        "color": "",
        "product_code": "",
        "url": "",
        "site": "",
        "offers": []
    }

    size_line = None                # Product Size:  "8:有货;10:无货"
    size_detail_line = None         # Product Size Detail: "8:1:EAN;10:0:EAN"
    price_line = None               # Product Price:
    adjusted_price_line = None      # Adjusted Price:

    for raw in lines:
        line = (raw or "").strip()

        if line.startswith("Product Name:"):
            info["style_name"] = line.split(":", 1)[1].strip()

        elif line.startswith("Product Color:"):
            val = line.split(":", 1)[1].strip()
            info["color"] = re.sub(r'^\-+\s*', '', val)

        elif line.startswith("Product Color Code:") or line.startswith("Product Code:"):
            val = line.split(":", 1)[1].strip()
            if val and val.lower() not in {"no data", "null"}:
                info["product_code"] = val

        elif line.startswith("Product URL:") or line.startswith("Source URL:"):
            info["url"] = line.split(":", 1)[1].strip()

        elif line.startswith("Site Name:"):
            info["site"] = line.split(":", 1)[1].strip()

        # 兼容旧 offer 行：size|price|stock|can_order
        elif "|" in line and line.count("|") == 3:
            try:
                raw_size, price, stock, avail = [x.strip() for x in line.split("|")]
                std_size = clean_size_for_barbour(raw_size)
                price_val = float(str(price).replace(",", "")) if price else 0.0
                stock_count = _to_stock_count(stock, avail)
                info["offers"].append({
                    "size": std_size,
                    "price": price_val,
                    "stock_count": stock_count
                })
            except Exception as e:
                print(f"⚠️ Offer 行解析失败: {line} -> {e}")
                continue

        elif line.startswith("Product Size:"):
            size_line = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size Detail:"):
            size_detail_line = line.split(":", 1)[1].strip()
        elif line.startswith("Adjusted Price:"):
            adjusted_price_line = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            price_line = line.split(":", 1)[1].strip()

    # 文件名兜底编码
    if not info["product_code"]:
        m = RE_CODE.search(filepath.stem.upper())
        if m:
            info["product_code"] = m.group(0)

    # 如果没有显式 offer 行，用 Size Detail / Size 生成
    if not info["offers"]:
        base_price = None
        if adjusted_price_line:
            base_price = _parse_price(adjusted_price_line)
        if base_price is None and price_line:
            base_price = _parse_price(price_line)
        if base_price is None:
            base_price = 0.0

        if size_detail_line:
            # 形如 "M:1:EAN;L:0:EAN" → 第二段数字就是库存数
            for token in filter(None, [t.strip() for t in size_detail_line.split(";")]):
                parts = [p.strip() for p in token.split(":")]
                if len(parts) >= 2:
                    raw_size = parts[0]
                    try:
                        stock_n = int(parts[1])
                    except Exception:
                        stock_n = 0
                    std_size = clean_size_for_barbour(raw_size)
                    info["offers"].append({
                        "size": std_size,
                        "price": base_price,
                        "stock_count": max(0, stock_n)
                    })
        elif size_line:
            # 形如 "S:有货;M:无货" → 有货=3，无货=0
            for token in filter(None, [t.strip() for t in size_line.split(";")]):
                if ":" not in token:
                    continue
                raw_size, status = token.split(":", 1)
                stock_count = _to_stock_count(status, None, default_has_stock=3)
                std_size = clean_size_for_barbour(raw_size)
                info["offers"].append({
                    "size": std_size,
                    "price": base_price,
                    "stock_count": stock_count
                })

    info["price_line"] = price_line
    info["adjusted_price_line"] = adjusted_price_line
    return info

# ----------（可选）旧的关键词匹配：保留以兼容 ----------
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
            SELECT product_code, style_name, match_keywords
            FROM barbour_products
            WHERE LOWER(color) LIKE '%%' || LOWER(%s) || '%%'
        """, (color.lower(),))
        candidates = cur.fetchall()
        best_match, best_score = None, 0
        for product_code, _title, match_kw in candidates:
            if not match_kw:
                continue
            toks = [w.lower() for w in match_kw] if isinstance(match_kw, list) else str(match_kw).lower().split()
            score = sum(1 for k in keywords if any(is_keyword_equivalent(k, mk) or k == mk for mk in toks))
            if score > best_score:
                best_match, best_score = product_code, score
        if best_match:
            return best_match
        return None

# ---------- 写库（只写 stock_count） ----------
def insert_offer(info, conn, missing_log: list) -> int:
    site = info.get("site") or ""
    offer_url = info.get("url") or ""
    style_name = info.get("style_name") or ""
    color = info.get("color") or ""
    product_code = info.get("product_code")
    if not product_code:
        # 如需自动匹配，可打开下一行：
        # product_code = find_color_code_by_keywords(conn, style_name, color)
        for offer in info.get("offers", []):
            missing_log.append(("", offer.get("size"), site, style_name, color, offer_url))

    offers = info.get("offers", [])
    if not offers:
        print("⚠️ 没有可导入的 offers（TXT 未包含 Offer List，且 Size/Detail 也未解析到）")
        return 0

    op = _parse_price(info.get("price_line"))
    dp = _parse_price(info.get("adjusted_price_line"))

    inserted = 0
    with conn.cursor() as cur:
        for offer in offers:
            raw_size = offer.get("size")
            size = clean_size_for_barbour(raw_size)
            if not size:
                print(f"⚠️ 无法清洗尺码: {raw_size}，跳过")
                continue

            price_gbp = (dp if dp is not None else op) if (dp is not None or op is not None) else float(offer.get("price", 0.0))
            original_price_gbp = op if op is not None else price_gbp
            stock_count = int(offer.get("stock_count") or 0)

            # 仅写 stock_count，不写 stock_status/can_order
            cur.execute("""
                INSERT INTO barbour_offers
                    (site_name, offer_url, size,
                     price_gbp, original_price_gbp, stock_count,
                     product_code, first_seen, last_seen, is_active, last_checked)
                VALUES (%s,%s,%s,%s,%s,%s,%s, NOW(), NOW(), TRUE, NOW())
                ON CONFLICT (site_name, offer_url, size) DO UPDATE SET
                    price_gbp          = EXCLUDED.price_gbp,
                    original_price_gbp = EXCLUDED.original_price_gbp,
                    stock_count        = EXCLUDED.stock_count,
                    product_code       = COALESCE(barbour_offers.product_code, EXCLUDED.product_code),
                    last_seen          = NOW(),
                    is_active          = TRUE,
                    last_checked       = NOW()
            """, (
                site, offer_url, size,
                price_gbp, original_price_gbp, stock_count,
                product_code if product_code else None
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

    run_start_ts = datetime.now()
    txt_dir = BARBOUR["TXT_DIRS"][supplier]
    conn = get_connection()
    files = sorted(Path(txt_dir).glob("*.txt"))
    missing = []

    total_files = 0
    total_rows = 0
    seen_sites = set()

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
            else:
                print(f"❗ 导入未写入数据: {fname}（无可用 offers）")
            if info.get("site"):
                seen_sites.add(info["site"])
        except Exception as e:
            print(f"❌ 导入失败: {fname}，错误: {e}")

    # 软删除：本次未见到的老记录 is_active = FALSE
    try:
        with conn.cursor() as cur:
            for site in (seen_sites or {supplier}):
                print(f"🧹 软删除站点未出现的旧记录：{site}")
                cur.execute("""
                    UPDATE barbour_offers
                    SET is_active = FALSE
                    WHERE site_name = %s
                      AND last_seen < %s
                """, (site, run_start_ts))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ 软删除出现异常：{e}")

    conn.close()

    print(f"\n📊 汇总：处理 {total_files} 个文件，成功写入 {total_rows} 条 offers。")

    if missing:
        output = Path(f"missing_products_{supplier}.csv")
        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["product_code", "size", "site", "style_name", "color", "offer_url"])
            writer.writerows(missing)
        print(f"⚠️ 有 {len(missing)} 个产品缺少 product_code，已记录到: {output}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python import_supplier_to_db_offers.py [supplier]")
    else:
        import_txt_for_supplier(sys.argv[1])
