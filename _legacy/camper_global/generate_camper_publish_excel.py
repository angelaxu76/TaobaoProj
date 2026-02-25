import pandas as pd
import psycopg2
from pathlib import Path
from openpyxl import Workbook
from collections import defaultdict
from config import BRAND_CONFIG
from common.core.translate import safe_translate
from common.core.price_utils import calculate_discount_price
from common.core.txt_parser import extract_product_info
from common.core.image_utils import copy_images_by_code

# -------------------- 获取淘宝已发布编码 --------------------
def get_existing_taobao_codes(store_excel_dir: Path):
    published_codes = set()
    for excel_file in store_excel_dir.glob("*.xlsx"):
        try:
            df = pd.read_excel(excel_file)
            if "商品编码" in df.columns:
                for code in df["商品编码"].dropna().tolist():
                    base_code = str(code).replace("_GLOBAL", "")
                    published_codes.add(base_code)
        except Exception as e:
            print(f"⚠️ 读取 {excel_file.name} 出错: {e}")
    return published_codes

# -------------------- 查询数据库候选编码 --------------------
def get_camper_publishable_codes(store_name: str, min_sizes=4):
    """
    获取 Camper Global 符合条件的编码：
    1. 未发布
    2. 至少 min_sizes 个尺码库存 >= 3
    3. 淘宝已发布的基础编码排除
    """
    cfg = BRAND_CONFIG["camper_global"]
    conn = psycopg2.connect(**cfg["PGSQL_CONFIG"])

    query = f"""
        SELECT product_code
        FROM {cfg["TABLE_NAME"]}
        WHERE is_published = FALSE
        GROUP BY product_code
        HAVING SUM(CASE WHEN stock_count >= 3 THEN 1 ELSE 0 END) >= {min_sizes}
    """
    df = pd.read_sql(query, conn)
    candidate_codes = df["product_code"].tolist()

    if not candidate_codes:
        print("⚠️ 没有符合条件的候选商品")
        return []

    # 淘宝 Excel 已发布的去重
    store_excel_dir = cfg["OUTPUT_DIR"] / store_name
    published_codes = get_existing_taobao_codes(store_excel_dir)

    final_codes = [c for c in candidate_codes if c.replace("_GLOBAL", "") not in published_codes]
    print(f"🟢 Camper 待发布商品数（排除重复后）: {len(final_codes)}")
    return final_codes

# -------------------- 找任意国家 TXT 文件 --------------------
def find_any_country_txt(txt_dir: Path, code: str) -> Path:
    base_code = code.replace("_GLOBAL", "")
    candidates = list(txt_dir.glob(f"{base_code}_*.txt"))
    if candidates:
        return candidates[0]
    return None

# -------------------- 主函数：生成 Excel --------------------
def generate_camper_publish_excel(store_name: str):
    cfg = BRAND_CONFIG["camper_global"]
    output_dir = cfg["OUTPUT_DIR"] / store_name
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = cfg["IMAGE_DIR"]
    image_output_dir = output_dir / "images"
    image_output_dir.mkdir(parents=True, exist_ok=True)

    # 获取候选编码
    codes = get_camper_publishable_codes(store_name)
    if not codes:
        return

    # 获取价格信息
    conn = psycopg2.connect(**cfg["PGSQL_CONFIG"])
    query_price = f"""
        SELECT product_code, gender, original_price_gbp, discount_price_gbp
        FROM {cfg["TABLE_NAME"]}
        WHERE product_code = ANY(%s)
    """
    df_price = pd.read_sql(query_price, conn, params=(codes,))
    price_map = {
        row["product_code"]: {
            "gender": row["gender"],
            "Price": row["original_price_gbp"],
            "AdjustedPrice": row["discount_price_gbp"]
        }
        for _, row in df_price.iterrows()
    }

    records = []
    txt_dir = cfg["TXT_DIR"]

    for code in codes:
        txt_path = find_any_country_txt(txt_dir, code)
        if not txt_path:
            print(f"⚠️ 缺少 TXT 文件: {code}")
            continue

        # 解析 TXT 获取基础信息
        info = extract_product_info(txt_path)
        info.update(price_map.get(code, {}))

        eng_title = info.get("Product Name", "No Data")
        cn_title = safe_translate(eng_title)
        upper = info.get("Upper Material", "No Data")
        price = calculate_discount_price(info)
        category = classify_shoe(eng_title + " " + info.get("Product Description", ""))

        records.append({
            "gender": info.get("gender", "").lower(),
            "category": category,
            "商品名称": cn_title,
            "商品编码": code,
            "价格": price,
            "upper material": upper,
            "英文名称": eng_title
        })

        copy_images_by_code(code, image_dir, image_output_dir)

    if not records:
        print("⚠️ 没有成功生成任何记录")
        return

    # 转 DataFrame 并检查列
    df = pd.DataFrame(records)
    expected_cols = ["商品名称", "商品编码", "价格", "upper material", "英文名称", "gender", "category"]
    if not all(col in df.columns for col in expected_cols):
        print("⚠️ 缺少关键列，终止生成")
        return
    df = df[expected_cols]

    # 按性别+类别拆分 Excel
    group_map = defaultdict(list)
    for rec in records:
        group_map[(rec["gender"], rec["category"])].append(rec["商品编码"])

    for (gender, category), code_group in group_map.items():
        part = df[df["商品编码"].isin(code_group)].drop(columns=["gender", "category"])
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

# -------------------- 分类函数 --------------------
def classify_shoe(text: str):
    text = text.lower()
    if any(k in text for k in ["boot", "boots", "chelsea", "ankle", "chukka"]):
        return "靴子"
    elif any(k in text for k in ["sandal", "sandals", "slide", "凉鞋", "open toe"]):
        return "凉鞋"
    else:
        return "其他"

# -------------------- 主入口 --------------------
if __name__ == "__main__":
    store = "Camper旗舰店"
    generate_camper_publish_excel(store)
