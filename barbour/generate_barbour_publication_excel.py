# -*- coding: utf-8 -*-
"""
生成 Barbour 外套夹克发布 Excel
"""

import sys
from pathlib import Path
import re
import openpyxl
from sqlalchemy import create_engine, text

from config import BRAND_CONFIG, BARBOUR, SETTINGS
from barbour.generate_barbour_taobao_title import generate_taobao_title
from common_taobao.core.price_utils import calculate_jingya_prices

# ========== 路径 ==========
TXT_DIR = BARBOUR["TXT_DIR_ALL"]
CODES_FILE = BARBOUR["OUTPUT_DIR"] / "codes.txt"
OUTPUT_FILE = BARBOUR["OUTPUT_DIR"]  / "barbour_publication.xlsx"

# ========== 正则规则 ==========
FIT_PAT = {
    "修身型": re.compile(r"\b(slim|tailored|trim)\b", re.I),
    "宽松型": re.compile(r"\b(relaxed|loose|oversized|boxy)\b", re.I),
}
NECK_PAT = [
    ("连帽", re.compile(r"\bhood(ed)?|detachable hood\b", re.I)),
    ("立领", re.compile(r"\bstand collar|funnel (neck|collar)|mock neck\b", re.I)),
    ("翻领", re.compile(r"\bcord(uroy)? collar|spread collar|point collar|shirt[- ]style collar\b", re.I)),
]
LEN_TXT = [
    ("短款", re.compile(r"\bshort(er)? length|cropped\b", re.I)),
    ("长款", re.compile(r"\blong(er)? length|longline\b", re.I)),
]
LEN_NUM = re.compile(r"(Back length|Sample length)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*cm", re.I)


def infer_fit_neck_length(name: str, desc: str = "", feature: str = ""):
    """根据英文描述/特征推断版型、领口设计、衣长"""
    text = " ".join([name or "", desc or "", feature or ""])

    # 版型
    fit = "标准"
    for zh, pat in FIT_PAT.items():
        if pat.search(text):
            fit = zh
            break

    # 领口
    neckline = "无"
    for zh, pat in NECK_PAT:
        if pat.search(text):
            neckline = zh
            break

    # 衣长
    length = None
    m = LEN_NUM.search(text)
    if m:
        cm = float(m.group(2))
        if cm < 66:
            length = "短款"
        elif cm > 78:
            length = "长款"
        else:
            length = "常规"
    if not length:
        for zh, pat in LEN_TXT:
            if pat.search(text):
                length = zh
                break
    if not length:
        length = "常规"

    return fit, neckline, length


# ========== SQL ==========
SQL_PRODUCT = text("""
    SELECT DISTINCT style_name, color
    FROM barbour_products
    WHERE color_code = :code
    ORDER BY style_name
    LIMIT 1
""")

SQL_OFFERS_ORDERABLE = text("""
    SELECT site_name, offer_url, price_gbp, stock_status, can_order, last_checked, size
    FROM offers
    WHERE color_code = :code
      AND can_order = TRUE
      AND (
            stock_status IS NULL
         OR stock_status ILIKE 'in stock'
         OR stock_status = '有货'
      )
      AND price_gbp IS NOT NULL
    ORDER BY price_gbp ASC
""")


def compute_rmb_price(min_gbp: float, exchange_rate: float) -> str:
    """调用公共 price util 计算淘宝售价（含成本）"""
    try:
        orig = float(min_gbp) if min_gbp is not None else 0.0
        disc = orig  # 目前没有独立折扣价
        base_price = max(orig, disc)
        untaxed, retail = calculate_jingya_prices(
            base_price=base_price,
            delivery_cost=7,   # 固定运费
            exchange_rate=exchange_rate
        )
        return untaxed, retail
    except Exception:
        return ""

def main():
    cfg = BRAND_CONFIG["barbour"]
    PGSQL = cfg["PGSQL_CONFIG"]

    engine = create_engine(
        f"postgresql+psycopg2://{PGSQL['user']}:{PGSQL['password']}@{PGSQL['host']}:{PGSQL['port']}/{PGSQL['dbname']}"
    )

    if not CODES_FILE.exists():
        print(f"❌ 未找到 codes.txt: {CODES_FILE}")
        sys.exit(1)

    codes = [line.strip() for line in CODES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Barbour Publication"

    header = [
        "商品编码", "Product Name EN", "颜色",
        "商品名称",
        "Min Price (GBP)", "鲸芽价格","淘宝价格",
        "版型", "领口设计", "衣长",
        "Sizes (In Stock)",  # ← 新增
        "Site", "Offer URL", "Stock Status", "Last Checked"
    ]
    ws.append(header)

    with engine.connect() as conn:
        for idx, code in enumerate(codes, 1):
            product = conn.execute(SQL_PRODUCT, {"code": code}).mappings().first()
            if not product:
                print(f"[{idx}/{len(codes)}] {code} ❌ 未找到产品信息")
                continue

            style_name = product["style_name"]
            color = product["color"]

            # 用 mappings() 获取 dict 列表
            offers_rows = list(conn.execute(SQL_OFFERS_ORDERABLE, {"code": code}).mappings())
            if not offers_rows:
                print(f"[{idx}/{len(codes)}] {code} ⚠️ 未找到可下单报价")
                continue

            # 计算“可下单 & in stock/有货”的尺码
            def _in_stock_can_order(row: dict) -> bool:
                s = (row.get("stock_status") or "").strip().lower()
                return bool(row.get("can_order")) and (not s or s.startswith("in stock") or s == "有货")

            sizes_in_stock = sorted({
                (row.get("size") or "").strip()
                for row in offers_rows
                if row.get("size") and _in_stock_can_order(row)
            })
            sizes_str = ", ".join(sizes_in_stock) if sizes_in_stock else ""

            # 最低价记录（SQL已按 price_gbp ASC）
            best = offers_rows[0]
            site_name = best["site_name"]
            offer_url = best["offer_url"]
            price_gbp = best["price_gbp"]
            stock_status = best["stock_status"]
            last_checked = best["last_checked"]

            # 生成中文标题
            title_cn = generate_taobao_title(style_name, color)

            # 售价计算
            rate = SETTINGS.get("EXCHANGE_RATE", 9.7)
            untaxed, retail = compute_rmb_price(price_gbp, exchange_rate=rate)

            # 推断版型/领口/衣长
            fit, neckline, coat_len = infer_fit_neck_length(style_name)

            row = [
                code, style_name, color,
                title_cn,
                float(price_gbp) if price_gbp is not None else "",
               untaxed,retail,
                fit, neckline, coat_len,
                sizes_str,  # ← 这列放这里
                site_name, offer_url, stock_status, last_checked
            ]
            ws.append(row)

            print(
                f"[{idx}/{len(codes)}] {code} → £{price_gbp} | 售价¥{untaxed} | 尺码[{sizes_str}] | {fit}/{neckline}/{coat_len} | {title_cn}")

    wb.save(OUTPUT_FILE)
    print(f"✅ Excel 已生成: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
