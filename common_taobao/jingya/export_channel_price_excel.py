import psycopg2
import pandas as pd
from config import CAMPER, CLARKS, ECCO, GEOX,BRAND_CONFIG
from common_taobao.core.price_utils import calculate_camper_untaxed_and_retail  # ✅ 引入统一定价逻辑



def export_channel_price_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE is_published = TRUE AND channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 🔽 ✅ 在这里加 debug
    print(f"📊 原始记录总数（未分组）: {len(df)}")
    print(f"📊 不重复的 channel_product_id 数量: {df['channel_product_id'].nunique()}")
    print(f"📊 缺失价格字段数量: {(df['original_price_gbp'].isnull() | df['discount_price_gbp'].isnull()).sum()}")

    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    print(df_grouped[["product_code", "original_price_gbp", "discount_price_gbp"]])
    # ✅ 使用统一价格函数替代 calculate_prices
    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(
        lambda row: pd.Series(
            calculate_camper_untaxed_and_retail(
                row["original_price_gbp"] if pd.notnull(row["original_price_gbp"]) else 0,
                row["discount_price_gbp"] if pd.notnull(row["discount_price_gbp"]) else 0,
                7,
                9.7
            )
        ),
        axis=1
    )

    df_prices_full = df_grouped[["channel_product_id", "product_code", "未税价格", "零售价"]]
    df_prices_full.columns = ["渠道产品ID", "商家编码", "未税价格", "零售价"]

    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices.xlsx"
    df_prices_full.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细: {out_path}")


    # === 仅仅输出txt_path文件中包含 channel_product_id的列表
import os
import psycopg2
import pandas as pd
from config import BRAND_CONFIG
from common_taobao.core.price_utils import calculate_camper_untaxed_and_retail


def export_channel_price_excel_from_txt(brand: str, txt_path: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    # === 读取 TXT 中的 channel_product_id 列表 ===
    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"❌ 未找到 TXT 文件: {txt_path}")

    with open(txt_path, "r", encoding="utf-8") as f:
        selected_ids = set(line.strip() for line in f if line.strip())

    if not selected_ids:
        raise ValueError("❌ TXT 文件中没有有效的 channel_product_id")

    # === 查询所有有效记录 ===
    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, original_price_gbp, discount_price_gbp, product_code
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # ✅ 强制转换为字符串以保证匹配成功
    df["channel_product_id"] = df["channel_product_id"].astype(str)

    # ✅ 过滤出 TXT 中指定的 ID
    df = df[df["channel_product_id"].isin(selected_ids)]

    if df.empty:
        print("⚠️ 没有匹配到任何 channel_product_id，对应的数据为空。")
        return

    # === 分组取第一条记录
    df_grouped = df.groupby("channel_product_id").agg({
        "original_price_gbp": "first",
        "discount_price_gbp": "first",
        "product_code": "first"
    }).reset_index()

    print(df_grouped[["product_code", "original_price_gbp", "discount_price_gbp"]])

    # === 使用统一定价逻辑
    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(
        lambda row: pd.Series(
            calculate_camper_untaxed_and_retail(
                row["original_price_gbp"] if pd.notnull(row["original_price_gbp"]) else 0,
                row["discount_price_gbp"] if pd.notnull(row["discount_price_gbp"]) else 0,
                7,
                9.7
            )
        ),
        axis=1
    )

    # === 输出列
    df_prices = df_grouped[["channel_product_id", "product_code", "未税价格", "零售价"]]
    df_prices.columns = ["渠道产品ID", "商家编码", "未税价格", "零售价"]

    out_path = config["OUTPUT_DIR"] / f"{brand.lower()}_channel_prices_filtered.xlsx"
    df_prices.to_excel(out_path, index=False)
    print(f"✅ 导出价格明细（指定列表）: {out_path}")


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



    print(df_grouped[["product_code", "original_price_gbp", "discount_price_gbp"]])
    # ✅ 使用统一价格函数
    df_grouped[["未税价格", "零售价"]] = df_grouped.apply(
        lambda row: pd.Series(
            calculate_camper_untaxed_and_retail(
                row["original_price_gbp"] if pd.notnull(row["original_price_gbp"]) else 0,
                row["discount_price_gbp"] if pd.notnull(row["discount_price_gbp"]) else 0,
                7,
                9.7
            )
        ),
        axis=1
    )

    df_grouped["product_code"] = df_grouped["product_code"].astype(str).str.strip().str.upper()
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
