import os
import psycopg2
import pandas as pd
from config import BRAND_CONFIG
from pathlib import Path
from common.pricing.price_utils import calculate_jingya_prices  # ✅ 定价计算核心逻辑

# ============ ✅ 品牌折扣配置 =============
BRAND_DISCOUNT = {
    "camper": 0.71,
    "geox": 0.85,
    "clarks": 1,
    # 默认：1.0（无折扣）
}

# ===== 新增：工具函数 =====
from typing import Optional, Set

def _load_excluded_codes(exclude_txt: Optional[Path]) -> Set[str]:
    excluded = set()
    if exclude_txt and exclude_txt.exists():
        with open(exclude_txt, "r", encoding="utf-8") as f:
            for line in f:
                code = line.strip()
                if code:
                    excluded.add(code.upper())
    return excluded


def get_brand_discount_rate(brand: str) -> float:
    return BRAND_DISCOUNT.get(brand.lower(), 1.0)

def get_brand_base_price(row, brand: str) -> float:
    original = row["original_price_gbp"] or 0
    discount = row["discount_price_gbp"] or 0
    base = min(original, discount) if original and discount else (discount or original)
    return base * get_brand_discount_rate(brand)

# ============ ✅ 公共导出函数 =============
# ============ ✅ 公共导出函数（更新） =============
def generate_channel_price_excel(
    df: pd.DataFrame,
    brand: str,
    out_path: Path,
    exclude_txt: Optional[Path] = None  # 👈 新增参数：排除的商品编码 TXT
):
    # 读取排除清单
    excluded_codes = _load_excluded_codes(exclude_txt)

    print(f"=== [DEBUG] groupby 前 df 行数: {len(df)} ===")
    print("样例 product_code:", df["product_code"].head(5).tolist())
    print("样例 channel_product_id:", df["channel_product_id"].head(5).tolist())

    # 先做分组
    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    print(f"=== [DEBUG] groupby 后 df_grouped 行数: {len(df_grouped)} ===")
    print("样例 product_code:", df_grouped["product_code"].head(5).tolist())
    print("样例 channel_product_id:", df_grouped["channel_product_id"].head(5).tolist())
    
    # 标准化商品编码后按排除表过滤
    df_grouped["product_code"] = df_grouped["product_code"].astype(str).str.strip().str.upper()
    if excluded_codes:
        df_grouped = df_grouped[~df_grouped["product_code"].isin(excluded_codes)]

    print("df_grouped rows:", len(df_grouped))
    print("df_grouped columns:", df_grouped.columns.tolist())
    print(df_grouped.head(5))
    # 价格计算
    df_grouped["Base Price"] = df_grouped.apply(lambda row: get_brand_base_price(row, brand), axis=1)
    # 第一步：调用 calculate_jingya_prices
    calc_results = df_grouped["Base Price"].apply(
        lambda price: calculate_jingya_prices(price, delivery_cost=7, exchange_rate=9.7)
    )

    print("=== DEBUG: 原始返回结果 ===")
    print(calc_results.head(10))   # 看看每行返回的是什么类型/结构

    # 第二步：把返回结果转换成 Series（展开成多列）
    expanded = calc_results.apply(pd.Series)

    print("=== DEBUG: 展开后的 DataFrame ===")
    print(expanded.head(10))
    print("expanded.shape:", expanded.shape)

    # 第三步：给列起名字，再赋值到目标 df
    expanded.columns = ["未税价格", "零售价"]
    df_grouped[["未税价格", "零售价"]] = expanded


    # 导出
    df_prices = df_grouped[["channel_product_id", "product_code", "Base Price", "未税价格", "零售价"]]
    df_prices.columns = ["渠道产品ID", "商家编码", "采购价（GBP）", "未税价格", "零售价"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_prices.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细: {out_path}（已排除 {len(excluded_codes)} 个编码）")


# ============ ✅ 函数 1：导出所有产品价格 =============
# ============ ✅ 函数 1：导出所有产品价格（更新默认排除路径） =============
def export_channel_price_excel(brand: str, exclude_txt: Optional[str] = None):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices.xlsx"

    # 默认从 OUTPUT_DIR/repulibcation/exclude_codes.txt 读取排除清单
    default_exclude = (config["OUTPUT_DIR"] / "repulibcation" / "exclude_codes.txt")
    exclude_path = Path(exclude_txt) if exclude_txt else default_exclude

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE is_published = TRUE AND channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"📊 原始记录总数: {len(df)}")
    print(f"🗂️ 使用排除清单: {exclude_path if exclude_path.exists() else '（未找到，跳过）'}")
    generate_channel_price_excel(df, brand, out_path, exclude_txt=exclude_path)


# ============ ✅ 函数 2：导出指定 TXT 列表价格 =============
def export_channel_price_excel_from_txt(brand: str, txt_path: str):
    """
    从 TXT 读取【商品编码】筛选条件生成价格表
    - TXT 每行写一个商品编码
    - 统一按 product_code 过滤
    """
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    out_dir = config["OUTPUT_DIR"]

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"❌ 未找到 TXT 文件: {txt_path}")

    # 读取商品编码
    with open(txt_path, "r", encoding="utf-8") as f:
        codes = {line.strip().upper() for line in f if line.strip()}

    if not codes:
        raise ValueError("❌ TXT 文件中没有有效的商品编码")

    conn = psycopg2.connect(**pg_cfg)
    try:
        query = f"""
            SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
            FROM {table_name}
            WHERE product_code IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
        print(f"=== SQL 读取后: {len(df)} 行 ===")

        df["product_code"] = df["product_code"].astype(str).str.strip().str.upper()
        print(f"=== 标准化 product_code 后: {len(df)} 行，样例: {df['product_code'].head(5).tolist()} ===")

        df = df[df["product_code"].isin(codes)]
        print(f"=== 按 TXT 里 {len(codes)} 个商品编码筛选后: {len(df)} 行 ===")

        out_path = out_dir / f"{brand.lower()}_channel_prices_by_codes.xlsx"
        print(f"🔎 使用【商品编码】筛选，共 {len(codes)} 个编码，匹配到 {len(df)} 行")
    finally:
        conn.close()

    if df.empty:
        print("⚠️ 没有匹配到任何记录。")
        return

    # 按统一逻辑导出
    generate_channel_price_excel(df, brand, out_path)


def export_channel_price_excel_from_channel_ids(brand: str, txt_path: str):
    """
    从 TXT 读取【channel_product_id】列表生成价格表
    - TXT 每行一个 channel_product_id（字符串原样匹配）
    - 统一调用 generate_channel_price_excel 导出
    输出：{OUTPUT_DIR}/{brand}_channel_prices_by_ids.xlsx
    """
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    out_dir = config["OUTPUT_DIR"]
    out_path = out_dir / f"{brand.lower()}_channel_prices_by_ids.xlsx"

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"❌ 未找到 TXT 文件: {txt_path}")

    # 读取 channel_product_id 清单
    with open(txt_path, "r", encoding="utf-8") as f:
        selected_ids = {line.strip() for line in f if line.strip()}

    if not selected_ids:
        raise ValueError("❌ TXT 文件中没有有效的 channel_product_id")

    conn = psycopg2.connect(**pg_cfg)
    try:
        query = f"""
            SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
            FROM {table_name}
            WHERE channel_product_id IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    # 过滤到这些 channel_product_id
    df["channel_product_id"] = df["channel_product_id"].astype(str)
    df = df[df["channel_product_id"].isin(selected_ids)]

    if df.empty:
        print("⚠️ 没有匹配到任何 channel_product_id。")
        return

    # 调用统一导出逻辑（自动计算 采购价→未税价→零售价）
    generate_channel_price_excel(df, brand, out_path)
    print(f"🔎 使用【channel_product_id】筛选，共 {len(selected_ids)} 个 ID，匹配 {len(df.groupby('channel_product_id'))} 个商品。")


# ============ ✅ 函数 3：导出 SKU 对应的价格（用于淘宝发布） =============
def export_all_sku_price_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    exclude_file = config["BASE"] / "document" / "excluded_product_codes.txt"
    excluded_names = set()
    if exclude_file.exists():
        with open(exclude_file, "r", encoding="utf-8") as f:
            excluded_names = set(line.strip().upper() for line in f if line.strip())

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    df_grouped["product_code"] = df_grouped["product_code"].astype(str).str.strip().str.upper()
    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(
        lambda row: pd.Series(calculate_jingya_prices(get_brand_base_price(row, brand), 7, 9.7)),
        axis=1
    )

    df_filtered = df_grouped[~df_grouped["product_code"].isin(excluded_names)]

    df_sku = df_filtered[["product_code", "零售价"]]
    df_sku.columns = ["商家编码", "优惠后价"]

    max_rows = 150
    total_parts = (len(df_sku) + max_rows - 1) // max_rows

    for i in range(total_parts):
        part_df = df_sku.iloc[i * max_rows: (i + 1) * max_rows]
        out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_sku_price_part{i+1}.xlsx"
        part_df.to_excel(out_path, index=False)
        print(f"✅ 导出: {out_path}（共 {len(part_df)} 条）")
