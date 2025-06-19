from common_taobao.classifier import classify_product
import os
import pandas as pd
from pathlib import Path
from collections import defaultdict
import shutil
import psycopg2
from config import PGSQL_CONFIG, CLARKS  # ✅ 统一配置
from clarks.core.GenerateExcel import generate_excel_from_codes  # ✅ 你已有的函数

# ============ 路径配置 ============
TXT_DIR = Path(CLARKS["TXT_DIR"])
OUTPUT_DIR = Path(CLARKS["OUTPUT_DIR"])
IMAGE_DIR = Path(CLARKS["IMAGE_DIR"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============ 提取标题与描述 ============
def get_title_and_description(code):
    txt_path = TXT_DIR / f"{code}.txt"
    if not txt_path.exists():
        return "", ""
    try:
        with open(txt_path, encoding="utf-8") as f:
            lines = f.readlines()
        title = ""
        desc = ""
        for line in lines:
            if line.startswith("商品标题："):
                title = line.replace("商品标题：", "").strip()
            elif line.startswith("商品描述："):
                desc = line.replace("商品描述：", "").strip()
        return title.lower(), desc.lower()
    except Exception as e:
        print(f"❌ 解析失败 {code}: {e}")
        return "", ""

# ============ 分类判断逻辑 ============
def classify_product(code):
    title, desc = get_title_and_description(code)
    text = f"{title} {desc}"
    if any(k in text for k in ["boot", "boots", "chelsea", "ankle", "desert"]):
        return "靴子"
    elif any(k in text for k in ["sandal", "sandals", "flip flop", "slide", "slipper", "slippers"]):
        return "凉拖鞋"
    else:
        return "其他"

# ============ 检查是否有图片 ============
def has_image(code):
    # 不再使用这个函数进行判断
    return False

# ============ 获取每个店铺的商品 ============
def get_eligible_products_by_store(conn):
    store_dict = {}
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT stock_name FROM clarks_inventory")
        store_names = [row[0] for row in cursor.fetchall()]

    for store in store_names:
        query = """
            SELECT product_name, gender
            FROM clarks_inventory
            WHERE stock_name = %s AND is_published = false
        """
        df = pd.read_sql(query, conn, params=(store,))
        grouped = df.groupby("product_name")
        valid_codes = []
        gender_map = {}

        for code, group in grouped:
            if group.shape[0] >= 3 and (group['gender'].iloc[0] in ['men', 'women']):
                valid_codes.append(code)
                gender_map[code] = group['gender'].iloc[0]

        store_dict[store] = {"codes": valid_codes, "gender": gender_map}
    return store_dict

# ============ 主逻辑 ============
def main():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    store_dict = get_eligible_products_by_store(conn)
    conn.close()

    print("🟡 跳过图片补全，仅准备发布数据")

    # === 按店铺分类并生成 Excel 与图片复制 ===
    for store, data in store_dict.items():
        grouped_codes = defaultdict(list)

        for code in data["codes"]:
            gender = data["gender"].get(code)
            if gender not in ["men", "women"]:
                continue
            category = classify_product(code)
            key = f"{gender}-{category}"
            grouped_codes[key].append(code)

        # === 复制图片到店铺根目录（不再按分类区分） ===
        image_output_dir = OUTPUT_DIR / store
        image_output_dir.mkdir(parents=True, exist_ok=True)

        for key, code_list in grouped_codes.items():
            if not code_list:
                continue
            filename = f"{store}_{key}.xlsx"
            output_path = OUTPUT_DIR / filename
            print(f"📦 正在生成: {filename} （{len(code_list)} 件）")
            generate_excel_from_codes(code_list, output_path)

            for code in code_list:
                matched = False
                for file in IMAGE_DIR.glob(f"{code}*.jpg"):
                    dst = image_output_dir / file.name
                    shutil.copy(file, dst)
                    matched = True
                    if dst.stat().st_size == 0:
                        print(f"⚠️ 警告：复制的图片为空文件：{dst.name}")
                for file in IMAGE_DIR.glob(f"{code}*.png"):
                    dst = image_output_dir / file.name
                    shutil.copy(file, dst)
                    matched = True
                    if dst.stat().st_size == 0:
                        print(f"⚠️ 警告：复制的图片为空文件：{dst.name}")
                if not matched:
                    print(f"❌ 图片缺失：{code}")

    print("✅ 所有 Excel 文件与图片复制完毕。")

if __name__ == "__main__":
    main()
