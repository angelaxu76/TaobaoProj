import math
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG, BRAND_DISCOUNT
from common_taobao.ingest.txt_parser import jingya_parse_txt_file
from channels.jingya.pricing.brand_price_rules import compute_brand_base_price
try:
    from common_taobao.core.price_utils import calculate_jingya_prices
except Exception:
    from common_taobao.core.price_utils import calculate_jingya_prices  # type: ignore


# --- debug ladder ---
try:
    from channels.jingya.pricing.discount_strategies_v2 import get_ladder_discount_price
except Exception:
    get_ladder_discount_price = None


MIN_STOCK_THRESHOLD = 2  # 小于该值的库存将置为0

def _safe_float(x) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except Exception:
        return 0.0

# def _brand_discount(brand: str) -> float:
#     return float(BRAND_DISCOUNT.get(brand.lower().strip(), 1.0))

# def _compute_base_price(original_gbp, discount_gbp, brand: str) -> float:
#     o = _safe_float(original_gbp)
#     d = _safe_float(discount_gbp)
#     if o > 0 and d > 0:
#         base_raw = min(o, d)
#     else:
#         base_raw = d if d > 0 else o
#     return base_raw * _brand_discount(brand)

import tempfile
from datetime import datetime
def import_txt_to_db_supplier(brand_name: str, exchange_rate: float = 9.7, delivery_cost: float = 7):
    brand_name = brand_name.lower()

    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    # 🧾 创建 debug log 文件（系统 temp 目录）
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(tempfile.gettempdir()) / f"price_debug_{brand_name}_{ts}.log"
    log_fp = log_path.open("w", encoding="utf-8")

    log_fp.write(
        "brand\tcode\tsize\t"
        "original_gbp\tdiscount_gbp\tladder_price\tbase_price\tjingya_price\ttaobao_price\n"
    )

    config = BRAND_CONFIG[brand_name]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    # 1️⃣ 解析 TXT
    parsed_records = []
    for file in Path(txt_dir).glob("*.txt"):
        recs = jingya_parse_txt_file(file)
        if recs:
            parsed_records.extend(recs)

    if not parsed_records:
        print("⚠️ 没有可导入的数据")
        return

    print(f"📥 共准备导入 {len(parsed_records)} 条记录")

    # 2️⃣ 重组插入数据
    enriched = []
    for t in parsed_records:
        (product_code, product_url, size, gender,
         ean, stock_count, original_price_gbp, discount_price_gbp, is_published,
         product_description, product_title, style_category) = t

        try:
            sc = int(stock_count) if stock_count is not None else 0
        except Exception:
            sc = 0
        if sc < MIN_STOCK_THRESHOLD:
            sc = 0


        o = _safe_float(original_price_gbp)
        d = _safe_float(discount_price_gbp)

        # 阶梯修正后的折扣价 d2（用于检查“阶梯抬价”有没有生效）
        if get_ladder_discount_price is not None:
            try:
                d2 = get_ladder_discount_price(o, d, brand_name)
            except Exception:
                d2 = None
        else:
            d2 = None

        base = compute_brand_base_price(brand_name, o, d)

        if base > 0:
            try:
                untaxed, retail = calculate_jingya_prices(base, delivery_cost=delivery_cost, exchange_rate=exchange_rate)
            except Exception:
                untaxed, retail = (None, None)
        else:
            untaxed, retail = (None, None)

        # ✅ 打印你要的三个价格 + 关键中间值

        log_fp.write(
            f"{brand_name}\t{product_code}\t{size}\t"
            f"{o:.2f}\t{d:.2f}\t"
            f"{(f'{d2:.2f}' if isinstance(d2, (int, float)) and d2 is not None else 'NA')}\t"
            f"{(f'{base:.2f}' if base else 'NA')}\t"
            f"{untaxed if untaxed is not None else 'NA'}\t"
            f"{retail if retail is not None else 'NA'}\n"
        )
        # print(
        #     f"[{brand_name}] code={product_code} size={size} "
        #     f"o={o:.2f} d={d:.2f} "
        #     f"d2={(f'{d2:.2f}' if isinstance(d2, (int, float)) and d2 is not None else 'NA')} "
        #     f"base={base:.2f} jingya={untaxed} taobao={retail}"
        # )

        enriched.append((
            product_code, product_url, size, gender,
            ean, sc,
            original_price_gbp, discount_price_gbp, is_published,
            product_description, product_title, style_category,
            untaxed, retail
        ))

    # 3️⃣ 入库
    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {table_name}")
            print(f"🧹 已清空表 {table_name}")

            sql = f"""
                INSERT INTO {table_name} (
                    product_code, product_url, size, gender,
                    ean, stock_count,
                    original_price_gbp, discount_price_gbp, is_published,
                    product_description, product_title, style_category,
                    jingya_untaxed_price, taobao_store_price
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_batch(cur, sql, enriched, page_size=500)
            print(f"✅ [{brand_name.upper()}] 数据已写入 {table_name}")

            # 4️⃣ 检查缺失 product_code
            cur.execute(f"SELECT DISTINCT product_code FROM {table_name}")
            existing_codes = {r[0] for r in cur.fetchall()}
            all_codes = {r[0] for r in enriched if r[0]}
            missing_codes = sorted(all_codes - existing_codes)

            if missing_codes:
                print(f"⚠️ 数据库中缺少 {len(missing_codes)} 个编码：")
                for c in missing_codes:
                    print("   ", c)
                Path("missing_codes.txt").write_text("\n".join(missing_codes), encoding="utf-8")
            else:
                print("✅ 所有 product_code 均已导入数据库。")

    print(f"🎯 [{brand_name.upper()}] 导入完成，共 {len(enriched)} 条。")
