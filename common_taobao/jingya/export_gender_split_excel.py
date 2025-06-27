import psycopg2
import pandas as pd
from config import CAMPER, CLARKS, ECCO, GEOX,BRAND_CONFIG

def export_gender_split_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT product_code, channel_product_id, gender
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    # 去重，保留每个 channel_product_id 的第一条记录
    df = df_raw.groupby("channel_product_id").agg({
        "product_code": "first",
        "gender": "first"
    }).reset_index()

    # 标准化字段
    df["product_code"] = df["product_code"].astype(str).str.strip()
    df["channel_product_id"] = df["channel_product_id"].astype(str).str.strip()
    df["gender"] = df["gender"].astype(str).str.strip().str.lower()

    # ✅ 按 gender 字段筛选
    df_male = df[df["gender"] == "男款"]
    df_female = df[df["gender"] == "女款"]

    df_male = df_male[["channel_product_id", "product_code"]]
    df_male.columns = ["渠道产品ID", "商品编码"]
    df_female = df_female[["channel_product_id", "product_code"]]
    df_female.columns = ["渠道产品ID", "商品编码"]

    out_base = config["OUTPUT_DIR"]
    df_male.to_excel(out_base / f"{brand.lower()}_男款商品列表.xlsx", index=False)
    df_female.to_excel(out_base / f"{brand.lower()}_女款商品列表.xlsx", index=False)
    print(f"✅ 导出男款商品数量: {len(df_male)}，女款商品数量: {len(df_female)}")

# 示例调用（pipeline 中手动调用）
# export_gender_split_excel("camper")