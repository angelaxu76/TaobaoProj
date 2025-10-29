# 原始脚本中的业务逻辑将被模块化到 common_taobao 中，当前脚本将作为品牌调用入口

import os
import shutil
import psycopg2
from config import CLARKS, PGSQL_CONFIG
from clarks.core.GenerateExcel import generate_excel_from_codes
from common_taobao.prepare_utils import (
    get_eligible_products_by_store,
    classify_product,
    get_title_and_description,
    copy_product_images
)

CATEGORY_KEYWORDS = {
    "靴子": ["boot", "chelsea", "ankle", "desert", "chukka"],
    "凉鞋": ["sandal", "slide", "open toe", "凉鞋"],
}


def prepare_products_for_publication(config: dict):
    txt_dir = config["TXT_DIR"]
    image_dir = config["IMAGE_DIR"]
    output_dir = config["OUTPUT_DIR"]
    store_dir = config["STORE_DIR"]
    table_name = config["TABLE_NAME"]

    conn = psycopg2.connect(**PGSQL_CONFIG)

    for store in store_dir.iterdir():
        if not store.is_dir():
            continue

        stock_name = store.name
        print(f"\n📦 准备发布店铺: {stock_name}")

        # 获取符合发布条件的商品数据
        df = get_eligible_products_by_store(conn, table_name, stock_name, txt_dir)
        if df.empty:
            print("⚠️ 无可发布商品")
            continue

        df["title"], df["desc"] = zip(*df.apply(lambda row: get_title_and_description(row["Product Code"], txt_dir), axis=1))
        df["gender"] = df["gender"].fillna("unknown")
        df["category"] = df.apply(lambda row: classify_product(row["title"], row["desc"], CATEGORY_KEYWORDS), axis=1)

        store_output_dir = output_dir / stock_name
        image_output_dir = store_output_dir / "images"
        image_output_dir.mkdir(parents=True, exist_ok=True)

        for (gender, category), group in df.groupby(["gender", "category"]):
            if len(group) == 0:
                continue
            label = f"{gender}-{category}"
            codes = group["Product Code"].tolist()
            generate_excel_from_codes(codes, store_output_dir / f"{label}.xlsx")
            for code in codes:
                copy_product_images(image_dir, image_output_dir, code)

        print("✅ 商品导出完成")


if __name__ == "__main__":
    prepare_products_for_publication(CLARKS)
