
import re

# ✅ 字段映射表（支持字段别名统一处理）
FIELD_MAP = {
    "Product Code": "product_code",
    "Product Name": "product_title",
    "Product Description": "product_description",
    "Product Gender": "gender",
    "Product Color": "color",
    "Color": "color",
    "Product Price": "original_price",
    "Original Price": "original_price",
    "Adjusted Price": "discount_price",
    "Actual Price": "discount_price",
    "Upper Material": "upper_material",
    "Product Material": "upper_material",
    "Product Size": "sizes",
    "Size Stock (EU)": "sizes",
    "Source URL": "url",
    "Product URL": "url"
}

def parse_txt_to_record(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    raw_data = {}
    for line in lines:
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        raw_data[key.strip()] = value.strip()

    # ✅ 应用字段映射
    data = {}
    for k, v in raw_data.items():
        mapped_key = FIELD_MAP.get(k)
        if mapped_key:
            data[mapped_key] = v

    product_code = data.get("product_code", "")
    product_url = data.get("url", "")
    gender = data.get("gender", "")
    title = data.get("product_title", "")

    price_str = re.sub(r"[^\d.]", "", data.get("original_price", ""))
    discount_str = re.sub(r"[^\d.]", "", data.get("discount_price", ""))
    original_price = float(price_str) if price_str else 0.0
    discount_price = float(discount_str) if discount_str else 0.0

    size_line = data.get("sizes", "")

    records = []
    for size_entry in size_line.split(';'):
        if not size_entry.strip() or ':' not in size_entry:
            continue
        size, status = size_entry.strip().split(':', 1)
        record = (
            product_code,      # ✅ 正确将 product_code 作为 product_name 字段入库
            product_url,
            size,
            gender,
            product_code,      # 先占位 skuid，在 import_txt_to_db 中会替换为实际 SKU
            status,
            original_price,
            discount_price,
            "总库存"           # stock_name (后续覆盖)
        )
        records.append(record)

    return records
