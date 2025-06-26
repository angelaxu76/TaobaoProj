import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
from config import CLARKS, CAMPER, ECCO, GEOX, DISCOUNT_EXCEL_DIR

BRANDS = {
    "clarks": CLARKS,
    "camper": CAMPER,
    "ecco": ECCO,
    "geox": GEOX,
}

def get_engine(pg_cfg):
    return create_engine(
        f"postgresql+psycopg2://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['dbname']}"
    )

def export_discount_products(brand_name: str, config: dict):
    print(f"▶ 正在处理品牌：{brand_name.upper()}")
    engine = get_engine(config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    fields = config["FIELDS"]
    DISCOUNT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

    # 构造 SQL
    sql = f"""
    SELECT {fields['product_code']} AS product_code,
           {fields['url']} AS url,
           {fields['discount_price']} AS discount_price_gbp,
           {fields['original_price']} AS original_price_gbp,
           {fields['size']} AS size,
           {fields['stock']} AS stock
    FROM {table}
    WHERE {fields['discount_price']} IS NOT NULL AND {fields['original_price']} IS NOT NULL
    """
    df = pd.read_sql(sql, engine)

    # 计算折扣
    df["discount"] = 1 - df["discount_price_gbp"] / df["original_price_gbp"]
    df["discount"] = df["discount"].round(2)

    # 判断“有货”
    if df["stock"].dtype == "O":
        in_stock_df = df[df["stock"] == "有货"]
    else:
        in_stock_df = df[df["stock"].astype(float) > 0]

    # 统计每个商品的有货尺码数
    stock_counts = in_stock_df.groupby("product_code")["size"].count().reset_index(name="num_in_stock")

    # 合并打折信息
    latest_price_df = df.drop_duplicates(subset=["product_code"], keep="first")[["product_code", "url", "discount_price_gbp", "discount"]]
    merged = latest_price_df.merge(stock_counts, on="product_code", how="inner")

    # 筛选：折扣 > 20%，尺码 ≥ 4
    selected = merged[(merged["discount"] > 0.2) & (merged["num_in_stock"] >= 4)]

    # 导出为一个品牌 Excel 文件
    if not selected.empty:
        selected.rename(columns={
            "product_code": "产品编码",
            "url": "URL",
            "discount": "折扣",
            "discount_price_gbp": "打折后价格",
            "num_in_stock": "几个尺码有货"
        }, inplace=True)

        selected["折扣"] = (selected["折扣"] * 100).astype(int).astype(str) + "%"
        output_path = DISCOUNT_EXCEL_DIR / f"{brand_name}_折扣商品.xlsx"
        selected.to_excel(output_path, index=False)
        print(f"✅ {brand_name.upper()}：已导出 {len(selected)} 个商品到 {output_path}")
    else:
        print(f"⚠️  {brand_name.upper()}：无符合条件商品，未生成文件。")

if __name__ == "__main__":
    for brand, cfg in BRANDS.items():
        export_discount_products(brand, cfg)

    print("🎉 所有品牌处理完成！")
