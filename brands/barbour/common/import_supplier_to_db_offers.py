
# import_supplier_to_db_offers.py  — 仅保留数字库存 stock_count（可覆盖）
import csv
import re
import unicodedata
import psycopg2
import argparse
from pathlib import Path
from brands.barbour.core.keyword_mapping import KEYWORD_EQUIVALENTS
from common.product.size_utils import clean_size_for_barbour  # 旧名保留
from brands.barbour.core.site_utils import canonical_site, assert_site_or_raise
from config import BARBOUR  # 已有导入就不要重复
from brands.barbour.core.supplier_price_rules import (
    strategy_all_ratio,
    strategy_ratio_when_no_discount,
)


# ---------- 小工具 ----------
_PRICE_NUM = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
RE_CODE = re.compile(r'[A-Z]{3}\d{3,4}[A-Z]{2,3}\d{2,3}')

# ==================== 仅新增：供货商“全价才打折”策略 ====================


# ========== 供货商价格策略（从 config + supplier_price_rules 统一调度） ==========

SUPPLIER_DISCOUNT_RULES = BARBOUR.get("SUPPLIER_DISCOUNT_RULES", {})

STRATEGY_MAP = {
    "all_ratio": strategy_all_ratio,
    "ratio_when_no_discount": strategy_ratio_when_no_discount,
}


def compute_supplier_sale_price(site_canon: str, op, dp) -> float:
    """
    根据站点（供货商）、原价 op、折扣价 dp，再结合 config 中的
    SUPPLIER_DISCOUNT_RULES，计算最终的 sale_price_gbp。

    - site_canon: canonical_site 之后的站点名，如 "outdoorandcountry"
    - op: 原价（TXT 中 Product Price）
    - dp: 折扣价（TXT 中 Adjusted Price / Now Price）

    返回值：已按 extra_ratio 和 shipping_fee 处理后的最终英镑价。
    """
    site_key = (site_canon or "").lower()
    rule = SUPPLIER_DISCOUNT_RULES.get(
        site_key,
        SUPPLIER_DISCOUNT_RULES.get("__default__", {}),
    )

    strategy_name = (rule.get("strategy") or "ratio_when_no_discount").lower()
    extra_ratio = rule.get("extra_ratio", 1.0)
    shipping_fee = rule.get("shipping_fee", 0.0)

    func = STRATEGY_MAP.get(strategy_name)
    if func is None:
        # 兜底：当配置错了（写了不存在的 strategy），
        # 就当「只用折扣价/原价 + 运费，不再额外打折」处理。
        return strategy_ratio_when_no_discount(op, dp, 1.0, shipping_fee)

    return func(op, dp, extra_ratio, shipping_fee)



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

    # 统一站点名（优先用 Site Name，找不到或不可识别时尝试用 URL 推断）
    site_raw = (info.get("site") or "").strip()
    url_raw  = (info.get("url") or "").strip()
    site_canon = canonical_site(site_raw) or canonical_site(url_raw)
    info["site"] = site_canon or ""

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

    site = assert_site_or_raise(info.get("site") or info.get("url") or "")
    if not product_code:
        # 如需自动匹配，可打开下一行：
        # product_code = find_color_code_by_keywords(conn, style_name, color)
        for offer in info.get("offers", []):
            missing_log.append(("", offer.get("size"), site, style_name, color, offer_url))

    offers = info.get("offers", [])
    if not offers:
        print("⚠️ 没有可导入的 offers（TXT 未包含 Offer List，且 Size/Detail 也未解析到）")
        return 0

    # === 仅替换开始：按供货商策略计算入库英镑价 ===
    # === 仅替换开始：按供货商策略计算 3 类价格 ===
    # 1）从 TXT 中解析原价和折扣价
    op = _parse_price(info.get("price_line"))              # TXT: Product Price → 原价
    dp = _parse_price(info.get("adjusted_price_line"))     # TXT: Adjusted Price / Now Price → 折扣价

    # 2）根据站点 + 策略配置计算最终 sale_price_gbp
    #    注意：这里的 site 已经是 canonical_site 之后的值（见上面 assert_site_or_raise）
    sale_price_gbp = compute_supplier_sale_price(site, op, dp)

    # 3）按你新定义的字段语义入库：
    #    - price_gbp            = TXT 原价
    #    - original_price_gbp   = TXT 折扣价
    #    - sale_price_gbp       = 供货商策略计算后的最终基准价
    price_gbp = op if op is not None else 0.0
    original_price_gbp = dp if dp is not None else None
    # === 仅替换结束 ===


    inserted = 0
    with conn.cursor() as cur:
        for offer in offers:
            raw_size = offer.get("size")
            size = clean_size_for_barbour(raw_size)
            if not size:
                print(f"⚠️ 无法清洗尺码: {raw_size}，跳过")
                continue


            stock_count = int(offer.get("stock_count") or 0)

            cur.execute("""
                INSERT INTO barbour_offers
                    (site_name, offer_url, size,
                     price_gbp, original_price_gbp, sale_price_gbp, stock_count,
                     product_code, first_seen, last_seen, is_active, last_checked)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s, NOW(), NOW(), TRUE, NOW())
                ON CONFLICT (site_name, offer_url, size) DO UPDATE SET
                    price_gbp          = EXCLUDED.price_gbp,
                    original_price_gbp = EXCLUDED.original_price_gbp,
                    sale_price_gbp     = EXCLUDED.sale_price_gbp,
                    stock_count        = EXCLUDED.stock_count,
                    product_code       = COALESCE(barbour_offers.product_code, EXCLUDED.product_code),
                    last_seen          = NOW(),
                    is_active          = TRUE,
                    last_checked       = NOW()
            """, (
                site, offer_url, size,
                price_gbp, original_price_gbp, sale_price_gbp, stock_count,
                product_code if product_code else None
            ))
            inserted += 1

    if inserted > 0:
        conn.commit()
    else:
        conn.rollback()
    return inserted

def import_txt_for_supplier(supplier: str, dryrun: bool = False, full_sweep: bool = True):
    supplier = canonical_site(supplier) or supplier
    if supplier not in BARBOUR["TXT_DIRS"]:
        print(f"❌ 未找到 supplier: {supplier}")
        return

    # ✅ 先建连接，再用它取数据库时间
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW()")
            run_start_ts = cur.fetchone()[0]

        txt_dir = BARBOUR["TXT_DIRS"][supplier]
        files = sorted(Path(txt_dir).glob("*.txt"))
        missing = []

        total_files = 0
        total_rows = 0
        seen_sites = set()

        from collections import defaultdict
        written_by_site = defaultdict(int)
        urls_by_site = defaultdict(set)

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
                # 记录本轮触达 URL + 写入计数（用于精准软删）
                site_for_del = canonical_site(info.get("site") or supplier) or (info.get("site") or supplier)
                url_for_del = info.get("url") or info.get("product_url")
                if url_for_del:
                    urls_by_site[site_for_del].add(url_for_del)
                if written > 0:
                    written_by_site[site_for_del] += written

            except Exception as e:
                print(f"❌ 导入失败: {fname}，错误: {e}")

        try:
            with conn.cursor() as cur:
                for site, cnt in written_by_site.items():
                    if cnt <= 0:
                        continue
                    url_list = list(urls_by_site.get(site, set()))
                    if not url_list:
                        continue

                    # ── 阶段 1：URL 作用域软删除 ────────────────────────────────
                    # 针对"本次抓到了该 URL，但某些 size 在 TXT 里消失了"的情况
                    print(f"🧹 [1/2] URL 作用域软删除（size 缺失）：{site} | URL数={len(url_list)}")
                    if dryrun:
                        cur.execute("""
                            SELECT site_name, offer_url, size, last_seen
                            FROM barbour_offers
                            WHERE site_name = %s
                              AND offer_url = ANY(%s)
                              AND last_seen < %s
                        """, (site, url_list, run_start_ts))
                        rows = cur.fetchall()
                        print(f"[DryRun] {len(rows)} rows would be soft-deleted (URL scope):")
                        for r in rows[:20]:
                            print(r)
                        if len(rows) > 20:
                            print(f"...共 {len(rows)} 行，已省略 {len(rows)-20} 行")
                    else:
                        cur.execute("""
                            UPDATE barbour_offers
                               SET is_active   = FALSE,
                                   stock_count = 0,
                                   last_checked = NOW()
                             WHERE site_name = %s
                               AND offer_url = ANY(%s)
                               AND last_seen  < %s
                        """, (site, url_list, run_start_ts))
                        print(f"   → 受影响行数: {cur.rowcount}")

                    # ── 阶段 2：全站点范围软删除 ─────────────────────────────────
                    # 针对"整个商品 URL 都没出现在本次 TXT 里（商品已下架）"的情况
                    # full_sweep=True 表示本次是完整批量抓取，可安全地清零所有未更新记录
                    if full_sweep:
                        print(f"🧹 [2/2] 全站点范围软删除（URL 整体消失）：{site}")
                        if dryrun:
                            cur.execute("""
                                SELECT site_name, offer_url, size, last_seen
                                FROM barbour_offers
                                WHERE site_name = %s
                                  AND last_seen < %s
                                  AND is_active = TRUE
                            """, (site, run_start_ts))
                            rows = cur.fetchall()
                            print(f"[DryRun] {len(rows)} rows would be soft-deleted (full sweep):")
                            for r in rows[:20]:
                                print(r)
                            if len(rows) > 20:
                                print(f"...共 {len(rows)} 行，已省略 {len(rows)-20} 行")
                        else:
                            cur.execute("""
                                UPDATE barbour_offers
                                   SET is_active   = FALSE,
                                       stock_count = 0,
                                       last_checked = NOW()
                                 WHERE site_name = %s
                                   AND last_seen  < %s
                                   AND is_active  = TRUE
                            """, (site, run_start_ts))
                            print(f"   → 受影响行数: {cur.rowcount}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"⚠️ 软删除出现异常：{e}")

        print(f"\n📊 汇总：处理 {total_files} 个文件，成功写入 {total_rows} 条 offers。")
        if missing:
            output = Path(f"missing_products_{supplier}.csv")
            with open(output, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["product_code", "size", "site", "style_name", "color", "offer_url"])
                writer.writerows(missing)
            print(f"⚠️ 有 {len(missing)} 个产品缺少 product_code，已记录到: {output}")

    finally:
        # ✅ 确保连接一定被关闭
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("supplier", help="supplier name (e.g., very, houseoffraser)")
    parser.add_argument("--dryrun", action="store_true", help="only print affected rows, do not update")
    args = parser.parse_args()

    # 把 dryrun 传给主函数
    import_txt_for_supplier(args.supplier, dryrun=args.dryrun)

