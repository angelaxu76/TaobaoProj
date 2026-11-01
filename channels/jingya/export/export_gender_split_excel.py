import psycopg2
import pandas as pd
from pathlib import Path
from config import BRAND_CONFIG

def export_recently_published_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]
    processed_dir = Path(config["OUTPUT_DIR"]) / "processed"

    # ✅ 收集 processed 目录下所有 Excel 文件中的商品编码
    published_codes = set()
    for file in processed_dir.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        print(f"📂 正在读取商品编码文件: {file.name}")
        df = pd.read_excel(file, dtype=str)
        if "商品编码" in df.columns:
            published_codes.update(df["商品编码"].dropna().astype(str).str.strip())
        elif "product_code" in df.columns:
            published_codes.update(df["product_code"].dropna().astype(str).str.strip())
        else:
            print(f"⚠️ 文件 {file.name} 中未找到“商品编码”列")

    if not published_codes:
        print("⚠️ 没有找到任何已发布商品编码")
        return

    # 🔍 查询数据库
    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT product_code, channel_product_id, gender
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
    """
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    df_raw["product_code"] = df_raw["product_code"].astype(str).str.strip()
    df_raw["channel_product_id"] = df_raw["channel_product_id"].astype(str).str.strip()
    df_raw["gender"] = df_raw["gender"].astype(str).str.strip().str.lower()

    # ✅ 筛选最近发布商品
    df = df_raw[df_raw["product_code"].isin(published_codes)]

    # 🚻 按性别拆分
    df_male = df[df["gender"] == "男款"][["channel_product_id", "product_code"]].drop_duplicates()
    df_male.columns = ["渠道产品ID", "商品编码"]

    df_female = df[df["gender"] == "女款"][["channel_product_id", "product_code"]].drop_duplicates()
    df_female.columns = ["渠道产品ID", "商品编码"]

    # 💾 导出 Excel
    out_base = config["OUTPUT_DIR"]
    out_base.mkdir(parents=True, exist_ok=True)
    df_male.to_excel(out_base / f"{brand.lower()}_最近发布_男款商品列表.xlsx", index=False)
    df_female.to_excel(out_base / f"{brand.lower()}_最近发布_女款商品列表.xlsx", index=False)

    print(f"✅ 导出最近发布商品：男款 {len(df_male)}，女款 {len(df_female)}")

import psycopg2
import pandas as pd
from pathlib import Path
from config import BRAND_CONFIG

def export_gender_split_excel(brand: str):
    config = BRAND_CONFIG[brand.lower()]
    pg_cfg = config["PGSQL_CONFIG"]
    table_name = config["TABLE_NAME"]

    conn = psycopg2.connect(**pg_cfg)
    query = f"""
        SELECT channel_product_id, product_code, gender
        FROM {table_name}
        WHERE channel_product_id IS NOT NULL
          AND channel_product_id <> ''
    """
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    # ✅ 标准化
    df_raw["channel_product_id"] = df_raw["channel_product_id"].astype(str).str.strip()
    df_raw["product_code"] = df_raw["product_code"].astype(str).str.strip()
    df_raw["gender"] = df_raw["gender"].astype(str).str.strip()

    # ✅ 按 channel_product_id 去重（保留第一条）
    df_unique = df_raw.drop_duplicates(subset=["channel_product_id"])

    # ✅ 男款 & 女款
    # 鞋类品牌 TXT 写中文（男款/女款），服装品牌（如 toast）写英文（Men/Women）
    gender_l = df_unique["gender"].str.lower()
    df_male = df_unique[gender_l.isin(["男款", "men", "male"])][["channel_product_id", "product_code"]]
    df_male.columns = ["渠道产品ID", "商品编码"]

    df_female = df_unique[gender_l.isin(["女款", "women", "female"])][["channel_product_id", "product_code"]]
    df_female.columns = ["渠道产品ID", "商品编码"]

    out_base = Path(config["OUTPUT_DIR"])
    out_base.mkdir(parents=True, exist_ok=True)
    file_male = out_base / f"{brand.lower()}_男款商品列表.xlsx"
    file_female = out_base / f"{brand.lower()}_女款商品列表.xlsx"

    df_male.to_excel(file_male, index=False)
    df_female.to_excel(file_female, index=False)

    print(f"✅ 导出完成：男款 {len(df_male)} 条，女款 {len(df_female)} 条，总计 {len(df_male) + len(df_female)} 条")
    print(f"📂 文件已保存至：\n  {file_male}\n  {file_female}")
# 示例调用（pipeline 中手动调用）
# export_gender_split_excel("camper")