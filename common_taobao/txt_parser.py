
from typing import List, Tuple
from pathlib import Path

def parse_txt_to_record(filepath: Path, brand: str) -> List[Tuple]:
    if brand == "camper":
        return parse_camper_txt(filepath)
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

def parse_camper_txt(filepath: Path) -> List[Tuple]:
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
    ean_line = ""
    url = ""
    feature = ""

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
        elif line.startswith("Product Size Detail:"):
            ean_line = line.split(":", 1)[1].strip()
        elif line.startswith("Source URL:"):
            url = line.split(":", 1)[1].strip()

    if not url:
        print(f"❌ 缺失 product_url，跳过编码: {product_code}")
        return []

    # 解析 EAN 对应的字典：{尺码: EAN}
    ean_dict = {}
    for ean_info in ean_line.split(";"):
        if not ean_info.strip():
            continue
        try:
            size, _, ean = ean_info.split(":")
            ean_dict[size.strip()] = ean.strip()
        except ValueError:
            continue

    for size_info in sizes_line.split(";"):
        if not size_info.strip():
            continue
        try:
            size, status = size_info.split(":")
            size = size.strip()
            status = status.strip()
            stock_status = "有货" if "有货" in status else "无货"
            ean = ean_dict.get(size, "")
            records.append((
                product_code, url, size, gender, "", stock_status,
                original_price, discount_price, "", ean
            ))
        except ValueError:
            continue

    return records

