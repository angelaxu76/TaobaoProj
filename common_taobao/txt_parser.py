
from typing import List, Tuple
from pathlib import Path

MIN_STOCK_THRESHOLD = 1  # 小于该值的库存将置为0

def parse_txt_to_record(filepath: Path, brand: str) -> List[Tuple]:
    if brand in ["camper", "clarks_jingya"]:  # 🟢 支持鲸芽统一格式
        return jingya_parse_txt_file(filepath)
    else:
        return parse_generic_txt(filepath)


def parse_generic_txt(filepath: Path) -> List[Tuple]:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    product_code = ""
    product_name = ""
    product_desc = ""
    gender = ""
    color = ""
    original_price = ""
    discount_price = ""
    material = ""
    sizes_line = ""
    url = ""
    feature = ""  # ✅ 新增变量

    for line in lines:
        line = line.strip()
        if line.startswith("Product Code:"):
            product_code = line.split(":", 1)[1].strip()
        elif line.startswith("Product Name:"):
            product_name = line.split(":", 1)[1].strip()
        elif line.startswith("Product Description:"):
            product_desc = line.split(":", 1)[1].strip()
        elif line.startswith("Product Gender:"):
            gender = line.split(":", 1)[1].strip()
        elif line.startswith("Product Color:"):
            color = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            original_price = line.split(":", 1)[1].strip().replace("£", "").strip()
        elif line.startswith("Adjusted Price:"):
            discount_price = line.split(":", 1)[1].strip()
        elif line.startswith("Product Material:"):
            material = line.split(":", 1)[1].strip()
        elif line.startswith("Feature:"):  # ✅ 新增解析
            feature = line.split(":", 1)[1].strip()
        elif line.startswith("Product Size:"):
            sizes_line = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:"):
            url = line.split(":", 1)[1].strip()

    for size_info in sizes_line.split(";"):
        if not size_info.strip():
            continue
        size, status = size_info.split(":")
        size = size.strip()
        status = status.strip()
        records.append((
            product_code, url, size, gender, "",  # 第5位占位空字符串
            "有货" if "有货" in status else "无货",
            original_price, discount_price, "",   # 第9位占位空字符串
        ))
    return records


def jingya_parse_txt_file(txt_path: Path) -> list:
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    info = {}
    size_detail_map = {}

    # ✅ 新增：先给三个新字段占位
    info["product_title"] = None         # Product Name
    info["product_description"] = None   # Product Description
    info["style_category"] = None        # Style Category

    for line in lines:
        line = line.strip()
        if line.startswith("Product Code:"):
            info["product_code"] = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:") or line.startswith("Product URL:"):
            info["product_url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Gender:"):
            info["gender"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Price:"):
            try:
                info["original_price_gbp"] = float(line.split(":", 1)[1].strip())
            except:
                info["original_price_gbp"] = 0.0
        elif line.startswith("Adjusted Price:"):
            try:
                info["discount_price_gbp"] = float(line.split(":", 1)[1].strip())
            except:
                info["discount_price_gbp"] = 0.0

        # ✅ 新增：三列的解析
        elif line.startswith("Product Name:"):
            info["product_title"] = line.split(":", 1)[1].strip()
        elif line.startswith("Product Description:"):
            info["product_description"] = line.split(":", 1)[1].strip()
        elif line.startswith("Style Category:"):
            info["style_category"] = line.split(":", 1)[1].strip()

        elif line.startswith("Product Size Detail:"):
            raw = line.split(":", 1)[1]
            for item in raw.split(";"):
                parts = item.strip().split(":")
                if len(parts) == 3:
                    size, stock_count, ean = parts
                    try:
                        stock_count = int(stock_count)
                    except:
                        stock_count = 0

                    # ✅ 库存阈值
                    if stock_count < MIN_STOCK_THRESHOLD:
                        stock_count = 0

                    size_detail_map[size] = {
                        "stock_count": stock_count,
                        "ean": ean
                    }

    records = []
    for size, detail in size_detail_map.items():
        records.append((
            info.get("product_code"),
            info.get("product_url"),
            size,
            info.get("gender"),
            detail["ean"],
            detail["stock_count"],
            info.get("original_price_gbp", 0.0),
            info.get("discount_price_gbp", 0.0),
            False,  # is_published

            # ✅ 追加三列（顺序与下方 INSERT 一一对应）
            info.get("product_description"),
            info.get("product_title"),
            info.get("style_category"),
        ))

    return records

