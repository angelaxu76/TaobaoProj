import os
import re
import shutil
import pandas as pd
from sqlalchemy import create_engine
from config import BRAND_CONFIG, SETTINGS
from common.pricing.price_utils import calculate_jingya_prices
from common.text.generate_taobao_title_v1 import generate_taobao_title

# ==== 固定参数 ====
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

# 条件参数（可调）
MIN_SIZES = 2         # 最少尺码数量



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

def generate_publication_excels(brand: str):
    brand = brand.lower()
    if brand not in BRAND_CONFIG:
        raise ValueError(f"❌ 不支持的品牌: {brand}")

    if brand == "clarks":
        MIN_TOTAL_STOCK = 11
    elif brand == "camper":
        MIN_TOTAL_STOCK = 11
    elif brand == "geox":
        MIN_TOTAL_STOCK = 11
    else:
        MIN_TOTAL_STOCK = 11  # 兜底默认值

    config = BRAND_CONFIG[brand]
    txt_folder = config["TXT_DIR"]
    output_base = config["OUTPUT_DIR"] / "publication_excels"
    image_src_dir = config["IMAGE_DIR"]
    image_dst_dir = output_base / "images"
    pg_cfg = config["PGSQL_CONFIG"]
    品牌 = brand

    # ==== 连接数据库 ====
    print(f"\n🔌 正在连接数据库，品牌：{brand.upper()}...")
    engine = create_engine(
        f"postgresql+psycopg2://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['dbname']}"
    )

    print("\n📊 正在查询符合条件的商品...")
    query = f"""
    WITH size_counts AS (
        SELECT product_code,
               COUNT(*) AS available_sizes,
               SUM(stock_count) AS total_stock
        FROM {config['TABLE_NAME']}
        WHERE stock_count > 1
        GROUP BY product_code
    ),
    publish_status AS (
        SELECT product_code,
               BOOL_OR(is_published) AS any_published
        FROM {config['TABLE_NAME']}
        GROUP BY product_code
    )
    SELECT DISTINCT ci.product_code,
           ci.original_price_gbp,
           ci.discount_price_gbp
    FROM {config['TABLE_NAME']} ci
    JOIN size_counts sc ON ci.product_code = sc.product_code
    JOIN publish_status ps ON ci.product_code = ps.product_code
    WHERE ps.any_published = FALSE
      AND sc.available_sizes >= {MIN_SIZES}
      AND sc.total_stock > {MIN_TOTAL_STOCK}
    """
    df_codes = pd.read_sql(query, engine)
    product_codes = df_codes["product_code"].tolist()
    print(f"✅ 获取到商品数: {len(product_codes)}")

    if not product_codes:
        print("⚠️ 没有符合条件的商品，任务结束")
        return

    # === 新增：检测重复 product_code 并打印出来 ===
    dup_codes = df_codes[df_codes.duplicated(subset="product_code", keep=False)]

    if not dup_codes.empty:
        print("\n❗❗ 检测到重复的商品编码（导致 set_index 失败）:")
        for c in sorted(dup_codes["product_code"].unique()):
            print(f"   ⚠ 重复编码: {c}")
            print(dup_codes[dup_codes["product_code"] == c])
        print("❗ 请检查以上编码的 TXT 或数据库记录。")

    # === 修复：自动去重，保留每个编码一行 ===
    df_codes_unique = (
        df_codes
        .sort_values(["product_code", "discount_price_gbp", "original_price_gbp"])
        .drop_duplicates(subset="product_code", keep="last")
    )

    # === 原来的代码 ===
    price_map = df_codes_unique.set_index("product_code")[["original_price_gbp", "discount_price_gbp"]].to_dict("index")




    gender_map = {
        k.strip().upper(): v for k, v in
        pd.read_sql(f"SELECT DISTINCT product_code, gender FROM {config['TABLE_NAME']}", engine)
        .dropna()
        .values
    }

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
        title_cn = generate_taobao_title(code, content, brand)["taobao_title"]

        print(f"[{code_clean}] EN: {title_en} → CN: {title_cn}")

        price_info = price_map.get(code, {"original_price_gbp": 0, "discount_price_gbp": 0})
        original = price_info.get("original_price_gbp", 0) or 0
        discount = price_info.get("discount_price_gbp", 0) or 0

        # 过滤掉为0的价格
        valid_prices = [p for p in [original, discount] if p > 0]

        # 如果有有效价格，取最小的那个，否则为0
        final_price = min(valid_prices) if valid_prices else 0

        try:
            _, rmb_price = calculate_jingya_prices(final_price, delivery_cost=7,exchange_rate=SETTINGS["EXCHANGE_RATE"])
        except:
            rmb_price = ""

        lining_info = content.lower()
        upper_info = content.lower()

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
    if df_all.empty:
        print("⚠️ 没有可生成的数据")
        return

    print("\n📊 分类统计：")
    print(df_all.groupby(["性别", "类目"]).size())

    os.makedirs(output_base, exist_ok=True)
    print("\n📤 正在导出 Excel 文件...")
    for (gender, category), sub_df in df_all.groupby(["性别", "类目"]):
        out_file = output_base / f"{brand}_{gender}_{category}.xlsx"
        if out_file.exists():
            out_file.unlink()
        sub_df.drop(columns=["性别", "类目"]).to_excel(out_file, index=False)
        print(f"✅ 导出：{out_file}")

    # 拷贝图片
    # 拷贝图片
    image_dst_dir.mkdir(parents=True, exist_ok=True)
    print("\n🖼️ 正在复制商品图片...")
    missing_codes = []  # <== 新增：收集缺图编码
    for code in product_codes:
        code_clean = code.strip().upper()
        matched_images = list(image_src_dir.glob(f"{code_clean}*.jpg"))
        if not matched_images:
            print(f"⚠️ 未找到图片: {code_clean}")
            missing_codes.append(code_clean)   # <== 记录缺图编码
            continue
        for img_path in matched_images:
            shutil.copy(img_path, image_dst_dir / img_path.name)

    # === 新增：写出 publication_codes.txt 与 missing_codes.txt ===
        # === 新增：写出 publication_codes.txt 与 missing_codes.txt ===
    pub_codes_file = config["OUTPUT_DIR"] / "publication_codes.txt"
    miss_codes_file = config["OUTPUT_DIR"] / "missing_codes.txt"

    # 所有符合条件的商品编码
    with open(pub_codes_file, "w", encoding="utf-8") as f:
        for code in sorted(set(product_codes)):
            f.write(f"{code}\n")
    print(f"📝 已写出商品编码列表: {pub_codes_file} ({len(product_codes)} 个)")

    # 缺图的编码
    with open(miss_codes_file, "w", encoding="utf-8") as f:
        for code in sorted(set(missing_codes)):
            f.write(f"{code}\n")
    print(f"📝 已写出缺图编码列表: {miss_codes_file} ({len(missing_codes)} 个)")



    print("\n✅ 所有操作完成。")

