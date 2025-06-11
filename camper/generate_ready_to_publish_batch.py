from GenerateExcelForTaoJingXiao import extract_product_codes_and_unappointProd_from_excel

import os
import re
import json
import time
import shutil
import psycopg2
import requests
import pandas as pd
import deepl
from datetime import datetime


# === 配置区域 ===
DB_CONFIG = {
    "host": "192.168.4.55",
    "port": 5432,
    "user": "postgres",
    "password": "madding2010",
    "dbname": "camper_inventory_db"
}
PUBLICATION_TXT_PATH = r"D:\\TB\\Products\\camper\\publication\\TXT"
PUBLICATION_IMAGE_PATH = r"D:\\TB\\Products\\camper\\ready_to_publish\\images"
IMAGE_OUTPUT_DIR = r"D:\TB\Products\camper\ready_to_publish\images"
OUTPUT_FOLDER = r"D:\\TB\\Products\\camper\\ready_to_publish\\current"

# 价格换算函数
def calculate_final_price(price):
    return round((price * 1.2 + 18) * 1.1 * 1.2 * 9.7)

# === 查询满足条件的商品编码（未发布 & 总库存 > 20） ===
def get_eligible_products():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT product_name, gender, SUM(stock_quantity) AS total_stock
        FROM camper_inventory
        WHERE is_published = FALSE
        GROUP BY product_name, gender
        HAVING SUM(stock_quantity) > 20
    """)
    rows = cursor.fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]

# === 提取 TXT 内容信息（含价格计算与材质提取） ===
def extract_txt_info(product_code):
    txt_file = os.path.join(PUBLICATION_TXT_PATH, f"{product_code}.txt")
    if not os.path.exists(txt_file):
        return None

    with open(txt_file, "r", encoding="utf-8") as f:
        content = f.read()

    def extract_field(pattern, default=""):
        match = re.search(pattern, content)
        return match.group(1).strip() if match else default

    price_str = extract_field(r"Product price:\s*(\d+(?:\.\d+)?)GBP")
    try:
        price = float(price_str)
        final_price = calculate_final_price(price)
    except:
        final_price = 0

    material = "无材质信息"
    features_match = re.search(r"Features:\n(.+?)\n\n", content, re.DOTALL)
    if features_match:
        try:
            features = json.loads(features_match.group(1))
            for f in features:
                if "Upper" in f.get("name", ""):
                    material = f.get("value", "").replace("<br/>", "").strip()
                    break
        except:
            pass

    return {
        "商品编码": product_code,
        "价格": final_price,
        "材质": material
    }

# === 复制图片文件 ===
def copy_images(product_code):
    os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
    IMAGE_SUFFIXES = ['_C.jpg', '_F.jpg', '_L.jpg', '_T.jpg', '_P.jpg']
    IMAGE_BASE_URL = "https://cloud.camper.com/is/image/YnJldW5pbmdlcjAx/"

    for suffix in IMAGE_SUFFIXES:
        filename = f"{product_code}{suffix}"
        src = os.path.join(PUBLICATION_IMAGE_PATH, filename)
        dst = os.path.join(IMAGE_OUTPUT_DIR, filename)

        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"📁 本地复制图片: {filename}")
        else:
            image_url = f"{IMAGE_BASE_URL}{product_code}{suffix}"  # ✅ 保留原编码
            print(f"🌐 尝试下载图片：{image_url}")

            try:
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200 and len(response.content) > 5000:
                    with open(dst, 'wb') as f:
                        f.write(response.content)
                    print(f"🖼️ 成功下载图片: {filename}")
                else:
                    print(f"⚠️ 图片不存在或是默认图（未下载）: {filename}")
            except Exception as e:
                print(f"❌ 下载失败: {filename}, 错误: {e}")

# === 主函数 ===
def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    eligible = get_eligible_products()
    gender_map = {"men": [], "women": [], "kids": []}

    for code, gender in eligible:
        print(f"📦 处理: {code} ({gender})")
        info = extract_txt_info(code)
        if not info:
            print(f"⚠️ 未找到 TXT 文件: {code}")
            pass
        gender_map.get(gender, gender_map["men"]).append(code)
        copy_images(code)

    for gender, codes in gender_map.items():
        if codes:
            txt_path = os.path.join(OUTPUT_FOLDER, f"待发布_{gender}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                for code in codes:
                    f.write(code + "\n")
            print(f"✅ 导出待发布编码列表：{txt_path}")

if __name__ == "__main__":
    main()


# === 调用生成男女款 Excel ===
TXT_DIR = os.path.join(OUTPUT_FOLDER)
TEXTS_FOLDER = r"D:\TB\Products\camper\publication\TXT"

for gender in ["men", "women"]:
    txt_path = os.path.join(TXT_DIR, f"待发布_{gender}.txt")
    if os.path.exists(txt_path):
        excel_path = os.path.join(TXT_DIR, f"{gender}_待发布商品.xlsx")
        extract_product_codes_and_unappointProd_from_excel(
            txt_path=txt_path,
            texts_folder=TEXTS_FOLDER,
            excel_path=excel_path
        )
