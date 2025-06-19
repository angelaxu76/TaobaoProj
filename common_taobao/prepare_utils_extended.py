from pathlib import Path
import pandas as pd
import shutil
import psycopg2
from common_taobao.translate import safe_translate
from common_taobao.price_utils import calculate_discount_price
from common_taobao.txt_parser import extract_product_info
from common_taobao.image_utils import copy_images_by_code

def get_publishable_product_codes(config: dict, store_name: str) -> list:
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table_name = config["TABLE_NAME"]
    txt_dir = config["TXT_DIR"]

    query = f"""
        SELECT DISTINCT product_name
        FROM {table_name}
        WHERE stock_name = %s
          AND is_published = FALSE
          AND product_name NOT IN (
              SELECT product_name FROM {table_name}
              WHERE stock_name = %s AND is_published = TRUE
          )
    """
    df = pd.read_sql(query, conn, params=(store_name, store_name))
    codes = df["product_name"].unique().tolist()

    def valid_stock(code):
        txt_path = txt_dir / f"{code}.txt"
        if not txt_path.exists():
            return False
        try:
            content = txt_path.read_text(encoding="utf-8")
            stock_line = next((line for line in content.splitlines() if line.startswith("Size Stock (EU):")), "")
            sizes = [s for s in stock_line.replace("Size Stock (EU):", "").split(";") if ":有货" in s]
            return len(sizes) >= 3
        except Exception:
            return False

    return [code for code in codes if valid_stock(code)]

def generate_product_excels(config: dict, store_name: str):
    from openpyxl import Workbook
    txt_dir = config["TXT_DIR"]
    output_dir = config["OUTPUT_DIR"] / store_name
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = config["IMAGE_DIR"]
    image_output_dir = output_dir / "images"
    image_output_dir.mkdir(parents=True, exist_ok=True)

    codes = get_publishable_product_codes(config, store_name)
    if not codes:
        print("⚠️ 没有可发布商品")
        return

    # 从数据库获取 gender + 正确价格字段
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    query = f"""
        SELECT product_name, gender, original_price_gbp, discount_price_gbp
        FROM {table}
        WHERE stock_name = %s
    """
    df = pd.read_sql(query, conn, params=(store_name,))
    price_map = {
        row["product_name"]: {
            "gender": row["gender"],
            "Price": row["original_price_gbp"],
            "AdjustedPrice": row["discount_price_gbp"]
        }
        for _, row in df.iterrows()
    }

    records = []
    for code in codes:
        info = extract_product_info(txt_dir / f"{code}.txt")
        info.update(price_map.get(code, {}))
        gender = info.get("gender", "unknown").lower()
        eng_title = info.get("Product Name", "No Data")
        cn_title = safe_translate(eng_title)
        upper = info.get("Upper Material", "No Data")
        price = calculate_discount_price(info)
        category = classify_shoe(eng_title + " " + info.get("Product Description", ""))
        records.append({
            "gender": gender,
            "category": category,
            "商品名称": cn_title,
            "商品编码": code,
            "价格": price,
            "up material": upper,
            "英文名称": eng_title
        })
        copy_images_by_code(code, image_dir, image_output_dir)

    df = pd.DataFrame(records)
    df = df[["商品名称", "商品编码", "价格", "up material", "英文名称", "gender", "category"]]

    from collections import defaultdict
    group_map = defaultdict(list)
    for rec in records:
        group_map[(rec["gender"], rec["category"])].append(rec["商品编码"])

    for (gender, category), code_list in group_map.items():
        part = df[df["商品编码"].isin(code_list)].drop(columns=["gender", "category"])
        if not part.empty:
            wb = Workbook()
            ws = wb.active
            ws.title = "商品发布"
            ws.append(part.columns.tolist())
            for row in part.itertuples(index=False):
                ws.append(row)
            save_path = output_dir / f"{gender}-{category}.xlsx"
            wb.save(save_path)
            print(f"✅ 已导出: {save_path.name}")

def classify_shoe(text: str):
    text = text.lower()
    if any(k in text for k in ["boot", "chelsea", "ankle", "chukka"]):
        return "靴子"
    elif any(k in text for k in ["sandal", "slide", "凉鞋", "open toe"]):
        return "凉鞋"
    else:
        return "其他"




def copy_images_for_store(config: dict, store_name: str, code_list: list):
    """
    将指定编码的所有图片从共享目录复制到店铺发布目录下的 images 文件夹中。
    匹配方式：只要文件名中包含该编码即可，不限于 _1.jpg 格式。
    """
    src_dir = config["IMAGE_DIR"]
    dst_dir = config["OUTPUT_DIR"] / store_name / "images"
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for code in code_list:
        for img in src_dir.glob(f"*{code}*.jpg"):
            shutil.copy(img, dst_dir / img.name)
            copied_count += 1

    print(f"✅ 图片拷贝完成，共复制 {copied_count} 张图 → {dst_dir}")

