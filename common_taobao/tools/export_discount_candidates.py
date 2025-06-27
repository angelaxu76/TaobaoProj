import re
from pathlib import Path
from typing import Dict

import pandas as pd
from sqlalchemy import create_engine

from config import (
    CLARKS,
    CAMPER,
    ECCO,
    GEOX,
    DISCOUNT_EXCEL_DIR,
    TAOBAO_STORES,
)

# ---------------------------------------------------------------------------
# Configuration ----------------------------------------------------------------
BRANDS = {
    "clarks": CLARKS,
    "camper": CAMPER,
    "ecco": ECCO,
    "geox": GEOX,
}

# ---------------------------------------------------------------------------
# Helpers ----------------------------------------------------------------------

def get_engine(pg_cfg):
    return create_engine(
        f"postgresql+psycopg2://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['dbname']}"
    )

def load_titles_from_txt(txt_dir: Path) -> pd.DataFrame:
    """扫描 TXT_DIR 下所有 TXT 文件, 提取 Product Name 作为标题"""
    records = []
    for file in txt_dir.glob("*.txt"):
        try:
            code = file.stem.strip()
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("Product Name:"):
                        title = line.split("Product Name:", 1)[-1].strip()
                        records.append((code, title))
                        break
        except Exception as e:
            print(f"⚠️  读取标题失败: {file.name} → {e}")
    return pd.DataFrame(records, columns=["product_code", "title"])


def classify_category(title) -> str:
    text = str(title).strip().lower() if pd.notna(title) else ""
    if re.search(r"\bboot(s)?\b", text):
        return "boots"
    if re.search(r"\bsandal(s)?\b", text):
        return "sandal"
    if re.search(r"\bloafer(s)?\b", text):
        return "loafer"
    if re.search(r"\btrainer(s)?\b|\bsneaker(s)?\b", text):
        return "sneaker"
    return "other"


def load_item_id_mapping(store_folder: Path) -> Dict[str, str]:
    """从店铺 Excel 文件(一个或多个)收集 商家编码→宝贝ID 映射"""
    mapping = {}
    if not store_folder.exists():
        return mapping

    for file in store_folder.glob("*.xls*"):
        try:
            df = pd.read_excel(file, dtype=str, usecols=["商家编码", "宝贝ID"])
            for _, row in df.iterrows():
                code = str(row.get("商家编码", "")).strip()
                item_id = str(row.get("宝贝ID", "")).strip()
                if code and item_id and code not in mapping:
                    mapping[code] = item_id
        except Exception as e:
            print(f"⚠️  读取店铺文件失败: {file.name} → {e}")
    return mapping

# ---------------------------------------------------------------------------
# Main export routine ----------------------------------------------------------

def export_discount_products(brand_name: str, config: dict):
    print(f"▶ 正在处理品牌：{brand_name.upper()}")

    engine = get_engine(config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    f = config["FIELDS"]
    txt_dir = config["TXT_DIR"]
    store_base = config["STORE_DIR"]

    DISCOUNT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

    sql = f"""
        SELECT {f['product_code']} AS product_code,
               {f['url']}         AS url,
               {f['discount_price']}  AS discount_price_gbp,
               {f['original_price']}  AS original_price_gbp,
               {f['size']}        AS size,
               {f['stock']}       AS stock,
               {f['gender']}      AS gender
        FROM   {table}
        WHERE  {f['discount_price']} IS NOT NULL
          AND  {f['original_price']} IS NOT NULL
    """
    df = pd.read_sql(sql, engine)

    # --- 1. 合并标题 -------------------------------------------------------------
    title_df = load_titles_from_txt(txt_dir)
    df = df.merge(title_df, on="product_code", how="left")

    # --- 2. 折扣与库存 -----------------------------------------------------------
    df["discount"] = 1 - df["discount_price_gbp"] / df["original_price_gbp"]
    df["discount"] = df["discount"].round(2)

    in_stock_df = (
        df[df["stock"] == "有货"] if df["stock"].dtype == "O" else df[df["stock"].astype(float) > 0]
    )
    stock_counts = (
        in_stock_df.groupby("product_code")["size"].count().reset_index(name="num_in_stock")
    )

    latest_price_df = (
        df.sort_values("discount_price_gbp")
          .drop_duplicates("product_code")
          [["product_code", "url", "discount_price_gbp", "discount", "title", "gender"]]
    )
    latest_price_df["category"] = latest_price_df["title"].apply(classify_category)

    merged = latest_price_df.merge(stock_counts, on="product_code", how="inner")
    selected = merged[(merged["discount"] > 0.2) & (merged["num_in_stock"] >= 4)]

    if selected.empty:
        print(f"⚠️  {brand_name.upper()}：无符合条件商品，未生成文件。")
        return

    # --- 3. 合并各店铺宝贝ID ----------------------------------------------------
    for store in TAOBAO_STORES:
        store_folder = store_base / store
        mapping = load_item_id_mapping(store_folder)
        col_name = f"{store}_宝贝ID"
        selected[col_name] = selected["product_code"].map(mapping).fillna("")

    # --- 4. 整理并导出 ----------------------------------------------------------
    selected = selected.sort_values("discount", ascending=False)

    selected.rename(
        columns={
            "product_code": "产品编码",
            "title": "商品标题",
            "gender": "性别",
            "category": "类别",
            "url": "URL",
            "discount": "折扣",
            "discount_price_gbp": "打折后价格",
            "num_in_stock": "几个尺码有货",
        },
        inplace=True,
    )

    selected["折扣"] = (selected["折扣"] * 100).astype(int).astype(str) + "%"

    output_path = DISCOUNT_EXCEL_DIR / f"{brand_name}_折扣商品.xlsx"
    selected.to_excel(output_path, index=False)
    print(f"✅ {brand_name.upper()}：已导出 {len(selected)} 个商品到 {output_path}")

# ---------------------------------------------------------------------------
# Entrypoint ------------------------------------------------------------------

if __name__ == "__main__":
    for brand, cfg in BRANDS.items():
        export_discount_products(brand, cfg)

    print("🎉 所有品牌处理完成！")
