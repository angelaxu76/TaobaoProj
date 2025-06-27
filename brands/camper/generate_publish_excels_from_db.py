import os
import re
import shutil
import pandas as pd
from pathlib import Path
from config import CAMPER, API_KEYS,SETTINGS
from sqlalchemy import create_engine
from common_taobao.core.price_utils import calculate_camper_untaxed_and_retail
from common_taobao.core.translate import safe_translate

# ==== 参数 ====
txt_folder = CAMPER["TXT_DIR"]
output_base = CAMPER["OUTPUT_DIR"] / "publication_excels"
image_src_dir = CAMPER["IMAGE_DIR"]
image_dst_dir = output_base / "images"
pg_cfg = CAMPER["PGSQL_CONFIG"]

上市季节 = "2025春季"
季节 = "春秋"
款式 = "休闲"
闭合方式 = ""
跟底款式 = "平底"
开口深度 = "浅口"
鞋头款式 = "圆头"
地区国家 = "英国"
发货时间 = "7"
运费模版 = "parcelforce"
第一计量单位 = "1"
第二计量单位 = "1"
销售单位 = "双"
品名 = "鞋"
海关款式 = "休闲鞋"
外底材料 = "EVA"
内底长度 = "27"
品牌 = "camper"

# ==== 连接数据库 ====
print("\n🔌 正在连接数据库...")
engine = create_engine(
    f"postgresql+psycopg2://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['dbname']}"
)

print("\n📊 正在查询符合条件的商品...")
query = """
WITH size_counts AS (
    SELECT product_code,
           COUNT(*) AS available_sizes,
           SUM(stock_count) AS total_stock
    FROM camper_inventory
    WHERE stock_count > 1
    GROUP BY product_code
)
SELECT DISTINCT ci.product_code,
       ci.original_price_gbp,
       ci.discount_price_gbp
FROM camper_inventory ci
JOIN size_counts sc ON ci.product_code = sc.product_code
WHERE ci.is_published = FALSE
  AND sc.available_sizes >= 4
  AND sc.total_stock > 20
"""
df_codes = pd.read_sql(query, engine)
product_codes = df_codes["product_code"].tolist()
print(f"✅ 获取到商品数: {len(product_codes)}")

price_map = df_codes.set_index("product_code")[["original_price_gbp", "discount_price_gbp"]].to_dict("index")

gender_map = {
    k.strip().upper(): v for k, v in
    pd.read_sql("SELECT DISTINCT product_code, gender FROM camper_inventory", engine)
    .dropna()
    .values
}

def extract_field(name, content):
    pattern = re.compile(rf"{name}\s*[:：]\s*(.+)", re.IGNORECASE)
    match = pattern.search(content)
    return match.group(1).strip() if match else ""

def get_category_v2(title: str, content: str, heel_height: str) -> str:
    t = title.lower()
    c = content.lower()
    if any(k in t for k in ["boot", "ankle", "chelsea"]):
        return "靴子"
    if any(k in t for k in ["sandal", "slide", "slipper", "mule", "flip-flop"]):
        return "凉鞋拖鞋"
    if heel_height in ["高跟(5-8cm)", "中跟(3-5cm)"]:
        return "其他休闲鞋"
    return "其他休闲鞋"

rows = []
print("\n📦 正在读取 TXT 并生成商品行数据...")
for idx, code in enumerate(product_codes, 1):
    code_clean = code.strip().upper()
    txt_path = txt_folder / f"{code_clean}.txt"
    if not txt_path.exists():
        print(f"❌ 缺少 TXT 文件: {txt_path}")
        continue

    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    title_en = extract_field("Product Name", content)
    title_cn = safe_translate(title_en)
    print(f"[{code_clean}] EN: {title_en} → CN: {title_cn}")

    price_info = price_map.get(code, {"original_price_gbp": 0, "discount_price_gbp": 0})
    original = price_info.get("original_price_gbp", 0) or 0
    discount = price_info.get("discount_price_gbp", 0) or 0
    base_price = min(original, discount) if original and discount else discount or original
    try:
        _, rmb_price = calculate_camper_untaxed_and_retail(base_price, exchange_rate=SETTINGS["EXCHANGE_RATE"])
    except:
        rmb_price = ""

    upper_info = content.lower()
    lining_info = content.lower()

    lining_material = "头层牛皮" if "leather" in lining_info else ("织物" if "recycled polyester" in lining_info else "")
    upper_material = "牛皮革" if "leather" in upper_info else ("织物" if "recycled polyester" in upper_info else "")

    hscode = "6403990090" if 'upper' in content.lower() and 'leather' in upper_info else "6405200090"

    match = re.search(r'Height[:：]?\s*(\d+\.?\d*)', content)
    if match:
        height = float(match.group(1))
        heel_height = "高跟(5-8cm)" if height > 5 else "中跟(3-5cm)" if height >= 3 else "低跟(1-3cm)"
    else:
        heel_height = ""

    row = {
        "英文标题": title_en,
        "标题": title_cn,
        "商品编码": code,
        "价格": rmb_price,
        "内里材质": lining_material,
        "帮面材质": upper_material,
        "上市季节": 上市季节,
        "季节": 季节,
        "款式": 款式,
        "闭合方式": 闭合方式,
        "跟底款式": 跟底款式,
        "开口深度": 开口深度,
        "后跟高": heel_height,
        "鞋头款式": 鞋头款式,
        "地区国家": 地区国家,
        "发货时间": 发货时间,
        "运费模版": 运费模版,
        "HSCODE": hscode,
        "第一计量单位": 第一计量单位,
        "第二计量单位": 第二计量单位,
        "销售单位": 销售单位,
        "品名": 品名,
        "海关款式": 海关款式,
        "外底材料": 外底材料,
        "内底长度": 内底长度,
        "品牌": 品牌,
        "性别": gender_map.get(code_clean, "男款"),
        "类目": get_category_v2(title_en, content, heel_height)
    }
    rows.append(row)

df_all = pd.DataFrame(rows)
print("\n📊 分类统计：")
print(df_all.groupby(["性别", "类目"]).size())

# 输出 Excel
os.makedirs(output_base, exist_ok=True)
print("\n📤 正在导出 Excel 文件...")
for (gender, category), sub_df in df_all.groupby(["性别", "类目"]):
    out_file = output_base / f"camper_{gender}_{category}.xlsx"
    if out_file.exists():
        out_file.unlink()
    sub_df.drop(columns=["性别", "类目"]).to_excel(out_file, index=False)
    print(f"✅ 导出：{out_file}")

# 拷贝图片
image_dst_dir.mkdir(parents=True, exist_ok=True)
print("\n🖼️ 正在复制商品图片...")
for code in product_codes:
    code_clean = code.strip().upper()
    matched_images = list(image_src_dir.glob(f"{code_clean}*.jpg"))
    if not matched_images:
        print(f"⚠️ 未找到图片: {code_clean}")
        continue
    for img_path in matched_images:
        shutil.copy(img_path, image_dst_dir / img_path.name)

print("\n✅ 所有操作完成。")
