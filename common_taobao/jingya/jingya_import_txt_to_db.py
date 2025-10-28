# jingya_import_txt_to_db.py 片段（替换 import_txt_to_db_supplier 函数）
import os
import math
import psycopg2
from pathlib import Path
from psycopg2.extras import execute_batch
from config import BRAND_CONFIG
from common_taobao.txt_parser import jingya_parse_txt_file

# ✅ 与导出脚本保持一致的价格工具 & 品牌折扣
try:
    from common_taobao.core.price_utils import calculate_jingya_prices
except Exception:
    from common_taobao.core.price_utils import calculate_jingya_prices  # type: ignore

BRAND_DISCOUNT = {
    "camper": 0.71,
    "geox": 0.98,
    "clarks_jingya": 1.0,
    "ecco": 0.9,
    # 其它品牌默认 1.0
}

MIN_STOCK_THRESHOLD = 1  # 小于该值的库存将置为0

def _safe_float(x) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except Exception:
        return 0.0

def _brand_discount(brand: str) -> float:
    return float(BRAND_DISCOUNT.get(brand.lower().strip(), 1.0))

def _compute_base_price(original_gbp, discount_gbp, brand: str) -> float:
    o = _safe_float(original_gbp)
    d = _safe_float(discount_gbp)
    if o > 0 and d > 0:
        base_raw = min(o, d)
    else:
        base_raw = d if d > 0 else o
    return base_raw * _brand_discount(brand)

def import_txt_to_db_supplier(brand_name: str):
    brand_name = brand_name.lower()
    if brand_name not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand_name}")

    config = BRAND_CONFIG[brand_name]
    txt_dir = config["TXT_DIR"]
    pg_config = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    # 1) 解析 TXT
    parsed_records = []
    for file in Path(txt_dir).glob("*.txt"):
        recs = jingya_parse_txt_file(file)
        if recs:
            parsed_records.extend(recs)

    if not parsed_records:
        print("⚠️ 没有可导入的数据")
        return

    print(f"📥 共准备导入 {len(parsed_records)} 条记录")

    # 2) 基于解析结果计算两种价格并重组为插入元组
    #    原有 jingya_parse_txt_file 返回顺序应为：
    #    (product_code, product_url, size, gender,
    #     ean, stock_count, original_price_gbp, discount_price_gbp, is_published,
    #     product_description, product_title, style_category)
    enriched = []
    for t in parsed_records:
        (product_code, product_url, size, gender,
         ean, stock_count, original_price_gbp, discount_price_gbp, is_published,
         product_description, product_title, style_category) = t

        # 库存阈值处理
        try:
            sc = int(stock_count) if stock_count is not None else 0
        except Exception:
            sc = 0
        if sc < MIN_STOCK_THRESHOLD:
            sc = 0

        # 计算 Base Price -> (untaxed, retail)
        base = _compute_base_price(original_price_gbp, discount_price_gbp, brand_name)
        if base > 0:
            try:
                untaxed, retail = calculate_jingya_prices(base, delivery_cost=7, exchange_rate=9.7)
            except Exception:
                untaxed, retail = (None, None)
        else:
            untaxed, retail = (None, None)

        # 组装含两个新价格字段的插入元组
        enriched.append((
            product_code, product_url, size, gender,
            ean, sc,
            original_price_gbp, discount_price_gbp, is_published,
            product_description, product_title, style_category,
            # 新增两列：
            untaxed,   # jingya_untaxed_price
            retail     # taobao_store_price
        ))

    # 3) 入库
    conn = psycopg2.connect(**pg_config)
    with conn:
        with conn.cursor() as cur:
            # 可选：清空表（如保留历史请注释掉）
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
            execute_batch(cur, sql, enriched, page_size=100)

    print(f"✅ [{brand_name.upper()}] 已完成导入，并写入 jingya_untaxed_price / taobao_store_price")
