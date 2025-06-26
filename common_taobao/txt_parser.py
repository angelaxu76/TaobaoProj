from pathlib import Path

# ✅ 标准字段映射（供 writer 使用）
FIELD_MAP = {
    "Product Code": "product_code",
    "Product Name": "product_title",
    "Product Description": "product_description",
    "Upper Material": "upper_material",
    "Color": "color",
    "Product URL": "url",
    "Gender": "gender",
    "Price": "original_price",
    "Adjusted Price": "discount_price",
    "Product Size": "sizes",
    "Product Size Detail": "size_detail"
}

def parse_txt_to_record(filepath: Path, brand_name=None) -> list:
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 通用字段
    product_code = ""
    product_name = ""
    product_description = ""
    upper_material = ""
    color = ""
    url = ""
    gender = ""
    original_price_gbp = None
    discount_price_gbp = None
    size_map = {}
    size_detail = {}

    for line in lines:
        line = line.strip()
        if line.startswith("Product Code:"):
            product_code = line.split(":", 1)[1].strip()
        elif line.startswith("Product Name:"):
            product_name = line.split(":", 1)[1].strip()
        elif line.startswith("Product Description:"):
            product_description = line.split(":", 1)[1].strip()
        elif line.startswith("Upper Material:"):
            upper_material = line.split(":", 1)[1].strip()
        elif line.startswith("Color:"):
            color = line.split(":", 1)[1].strip()
        elif line.startswith("Product URL:"):
            url = line.split(":", 1)[1].strip()
        elif line.startswith("Gender:"):
            gender = line.split(":", 1)[1].strip()
        elif line.startswith("Price:"):
            try:
                original_price_gbp = float(line.split(":", 1)[1].strip())
            except:
                original_price_gbp = None
        elif line.startswith("Adjusted Price:"):
            try:
                discount_price_gbp = float(line.split(":", 1)[1].strip())
            except:
                discount_price_gbp = None
        elif line.startswith("Product Size:"):
            parts = line.replace("Product Size:", "").strip().split(";")
            for p in parts:
                if ":" in p:
                    size, status = p.split(":", 1)
                    size_map[size.strip()] = status.strip()
        elif line.startswith("Product Size Detail:"):
            parts = line.replace("Product Size Detail:", "").strip().split(";")
            for p in parts:
                size, status, count, ean = p.split(":")
                size_detail[size.strip()] = {
                    "stock_status": status.strip(),
                    "stock_count": int(count.strip()),
                    "ean": ean.strip()
                }

    for size, status in size_map.items():
        if brand_name == "camper":
            ean = size_detail.get(size, {}).get("ean", "")
            record = (
                product_name,
                url,
                size,
                gender,
                product_code,
                status,
                original_price_gbp,
                discount_price_gbp,
                None,  # stock_name 外部补充
                ean
            )
        else:
            record = (
                product_name,
                url,
                size,
                gender,
                product_code,
                status,
                original_price_gbp,
                discount_price_gbp,
                None  # stock_name 外部补充
            )
        records.append(record)

    return records
