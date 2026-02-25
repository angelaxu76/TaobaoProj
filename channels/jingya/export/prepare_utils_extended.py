# -*- coding: utf-8 -*-
"""
prepare_utils_extended.py  —— 发布用 Excel 生成器（已对接“最新标题&价格脚本”）
- 标题：使用 generate_taobao_title.generate_taobao_title()
- 价格：使用本地 price_utils.calculate_discount_price()
- 其余：延续原有数据流、分组导出与图片拷贝逻辑
"""

import pandas as pd
import shutil
import psycopg2

# ===== 你原有的公共函数（保留） =====
from common.core.translate import safe_translate
from common.core.txt_parser import extract_product_info
from common.core.image_utils import copy_images_by_code

# ===== 替换为你的“最新”脚本 =====
from common.core.price_utils import calculate_discount_price            # 最新价格计算（本地文件）
from common.text.generate_taobao_title import generate_taobao_title     # 最新淘宝标题（本地文件）


def get_publishable_product_codes(config: dict, store_name: str) -> list:
    """
    从数据库筛选出该店铺未发布过、且 TXT 中 “:有货” 尺码数量 >=3 的商品编码
    """
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table_name = config["TABLE_NAME"]
    txt_dir = config["TXT_DIR"]

    query = f"""
        SELECT product_code
        FROM {table_name}
        WHERE stock_name = %s AND is_published = FALSE
        GROUP BY product_code
        HAVING COUNT(*) = COUNT(*)
            AND product_code NOT IN (
                SELECT DISTINCT product_code FROM {table_name}
                WHERE stock_name = %s AND is_published = TRUE
            )
    """
    df = pd.read_sql(query, conn, params=(store_name, store_name))
    candidate_codes = df["product_code"].unique().tolist()

    def has_3_or_more_instock(code):
        try:
            txt_path = txt_dir / f"{code}.txt"
            if not txt_path.exists():
                return False
            lines = txt_path.read_text(encoding="utf-8").splitlines()
            size_line = next((line for line in lines if line.startswith("Product Size:")), "")
            return size_line.count(":有货") >= 3
        except Exception:
            return False

    result = [code for code in candidate_codes if has_3_or_more_instock(code)]
    print(f"🟢 店铺【{store_name}】待发布商品数: {len(result)}")
    return result


def generate_product_excels(config: dict, store_name: str):
    """
    为指定店铺输出多个 Excel（按 gender + category 分文件），
    并将对应编码图片拷贝到店铺发布目录的 images/ 下。
    """
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

    # 从数据库获取 gender + 英镑价格（原价/折扣价），写入 info 供价格函数计算
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    query = f"""
        SELECT product_code, gender, original_price_gbp, discount_price_gbp
        FROM {table}
        WHERE stock_name = %s
    """
    df_price = pd.read_sql(query, conn, params=(store_name,))
    price_map = {
        row["product_code"]: {
            "gender": row["gender"],
            "Price": row["original_price_gbp"],
            "AdjustedPrice": row["discount_price_gbp"]
        }
        for _, row in df_price.iterrows()
    }

    brand_key = (config.get("BRAND") or config.get("brand") or table).lower()

    records = []
    for code in codes:
        # 1) 汇集 TXT 信息 + DB 价格字段
        info = extract_product_info(txt_dir / f"{code}.txt")
        info.update(price_map.get(code, {}))

        gender = (info.get("gender") or "unknown").lower()
        eng_title = info.get("Product Name", "No Data")
        desc = info.get("Product Description", "")
        upper = (
            info.get("Upper Material")
            or info.get("Product Material")
            or info.get("upper material")
            or info.get("Material")
            or "No Data"
        )

        color = info.get("Product Color", info.get("color", ""))

        # 2) 计算价格（走你最新规则）
        price = calculate_discount_price(info)  # 优先 AdjustedPrice，按你现行公式/档位+进位

        # 3) 生成淘宝标题（走你最新规则）
        #    按你的 title 解析方式，拼接 content 让其内部抽取字段
        content_lines = []
        for k in ["Product Name", "Product Description", "Product Material", "Product Color", "Product Gender"]:
            v = (info.get(k) or "").strip()
            if v:
                content_lines.append(f"{k}: {v}")
        content = "\n".join(content_lines) if content_lines else ""

        title_dict = generate_taobao_title(product_code=code, content=content, brand_key=brand_key)
        cn_title = title_dict.get("taobao_title") or title_dict.get("title_cn")

        # 回退：若异常或空值，用机翻英文名兜底
        if not cn_title:
            cn_title = safe_translate(eng_title)

        # 4) 分类（轻修：避免此前 "boots""chelsea" 拼接 bug）
        category = classify_shoe(f"{eng_title} {desc}")

        # 5) 累积记录 + 图片拷贝
        records.append({
            "gender": gender,
            "category": category,
            "商品名称": cn_title,
            "商品编码": code,
            "价格": price,
            "upper material": upper,
            "英文名称": eng_title
        })
        copy_images_by_code(code, image_dir, image_output_dir)

    # 6) 导出多个 Excel（按 gender+category 分文件）
    df = pd.DataFrame(records)
    df = df[["商品名称", "商品编码", "价格", "upper material", "英文名称", "gender", "category"]]

    from collections import defaultdict
    group_map = defaultdict(list)
    for rec in records:
        group_map[(rec["gender"], rec["category"])].append(rec["商品编码"])

    for (gen, cat), code_list in group_map.items():
        part = df[df["商品编码"].isin(code_list)].drop(columns=["gender", "category"])
        if not part.empty:
            wb = Workbook()
            ws = wb.active
            ws.title = "商品发布"
            ws.append(part.columns.tolist())
            for row in part.itertuples(index=False):
                ws.append(row)
            save_path = output_dir / f"{gen}-{cat}.xlsx"
            wb.save(save_path)
            print(f"✅ 已导出: {save_path.name}")


def classify_shoe(text: str):
    """
    简单鞋类分类：靴子 / 凉鞋 / 其他
    """
    text = (text or "").lower()
    if any(k in text for k in ["boot", "boots", "chelsea", "ankle", "chukka"]):
        return "靴子"
    elif any(k in text for k in ["sandal", "sandals", "slide", "凉鞋", "open toe", "slipper", "mule"]):
        return "凉鞋"
    else:
        return "其他"


def copy_images_for_store(config: dict, store_name: str, code_list: list):
    """
    将指定编码的所有图片从共享目录复制到店铺发布目录下的 images 文件夹中。
    如果某个编码没有匹配到任何图片，则记录到 missing_images.txt。
    """
    src_dir = config["IMAGE_DIR"]
    dst_dir = config["OUTPUT_DIR"] / store_name / "images"
    dst_dir.mkdir(parents=True, exist_ok=True)

    missing_file = config["OUTPUT_DIR"] / store_name / "missing_images.txt"
    missing_file.parent.mkdir(parents=True, exist_ok=True)
    missing_codes = []

    copied_count = 0
    for code in code_list:
        matched = False
        for img in src_dir.glob(f"*{code}*.jpg"):
            shutil.copy(img, dst_dir / img.name)
            copied_count += 1
            matched = True
        if not matched:
            missing_codes.append(code)

    if missing_codes:
        with open(missing_file, "w", encoding="utf-8") as f:
            for code in missing_codes:
                f.write(code + "\n")
        print(f"⚠️ 缺图商品编码已记录: {missing_file}（共 {len(missing_codes)} 条）")

    print(f"✅ 图片拷贝完成，共复制 {copied_count} 张图 → {dst_dir}")


def get_publishable_codes_for_supplier(config: dict) -> list:
    conn = psycopg2.connect(**config["PGSQL_CONFIG"])
    table = config["TABLE_NAME"]
    txt_dir = Path(config["TXT_DIR"])

    # 1. 数据库层面筛选：未发布、男女款、有货尺码 ≥4、总库存 >30
    query = f"""
        SELECT product_code
        FROM {table}
        WHERE gender IN ('男款', '女款')
          AND is_published = FALSE
          AND stock_count > 0
        GROUP BY product_code
        HAVING COUNT(DISTINCT size) >= 4
           AND SUM(stock_count) > 30
    """
    df = pd.read_sql(query, conn)
    conn.close()
    candidate_codes = df["product_code"].unique().tolist()

    # 2. TXT 文件校验：至少有 4 个 ":有货"
    def txt_has_4_sizes(code: str) -> bool:
        txt_path = txt_dir / f"{code}.txt"
        if not txt_path.exists():
            return False
        try:
            lines = txt_path.read_text(encoding="utf-8").splitlines()
            size_line = next((line for line in lines if line.startswith("Product Size:")), "")
            return size_line.count(":有货") >= 4
        except:
            return False

    valid_codes = [code for code in candidate_codes if txt_has_4_sizes(code)]

    print(f"🟢 Camper 供货商模式下可发布商品数量：{len(valid_codes)}")
    return valid_codes
