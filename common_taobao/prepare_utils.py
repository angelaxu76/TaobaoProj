import os
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime


def get_eligible_products_by_store(conn, table_name, stock_name, txt_dir):
    query = f"""
        SELECT DISTINCT product_name, gender
        FROM {table_name}
        WHERE stock_name = %s AND is_published = FALSE
    """
    df = pd.read_sql(query, conn, params=(stock_name,))
    df.rename(columns={"product_name": "Product Code"}, inplace=True)

    def has_sufficient_stock(code):
        txt_file = txt_dir / f"{code}.txt"
        if not txt_file.exists():
            return False
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                content = f.read()
            stock_line = next((line for line in content.splitlines() if line.startswith("Size Stock (EU):")), "")
            size_entries = stock_line.replace("Size Stock (EU):", "").strip().split(";")
            instock = [s for s in size_entries if ":有货" in s]
            return len(instock) >= 3
        except Exception:
            return False

    df = df[df["Product Code"].apply(has_sufficient_stock)]
    return df


def get_title_and_description(code, txt_dir):
    path = txt_dir / f"{code}.txt"
    title = desc = "No Data"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Product Name:"):
                    title = line.replace("Product Name:", "").strip()
                elif line.startswith("Product Description:"):
                    desc = line.replace("Product Description:", "").strip()
    return title, desc


def classify_product(title, desc, keyword_dict):
    text = f"{title} {desc}".lower()
    for category, keywords in keyword_dict.items():
        if any(kw.lower() in text for kw in keywords):
            return category
    return "其他"


def copy_product_images(src_dir: Path, dst_dir: Path, code: str):
    for i in range(1, 10):  # 最多拷贝9张图
        image_name = f"{code}_{i}.jpg"
        src = src_dir / image_name
        if src.exists():
            shutil.copy(src, dst_dir / image_name)
