import re

def parse_txt_to_record(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    data = {}
    for line in lines:
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        data[key.strip()] = value.strip()

    product_name = data.get("Product Name", "")
    product_code = data.get("Product Code", "")
    product_url = data.get("Source URL", "")
    gender = data.get("Product Gender", "")

    # 容错处理价格为空或 No Data 的情况
    price_str = re.sub(r"[^\d.]", "", data.get("Product Price", ""))
    discount_str = re.sub(r"[^\d.]", "", data.get("Adjusted Price", ""))
    original_price = float(price_str) if price_str else 0.0
    discount_price = float(discount_str) if discount_str else 0.0

    size_line = data.get("Product Size", "")

    records = []
    for size_entry in size_line.split(';'):
        if not size_entry.strip():
            continue
        if ':' not in size_entry:
            continue
        size, status = size_entry.strip().split(':', 1)
        record = (
            product_name,      # product_name
            product_url,       # product_url
            size,              # size
            gender,            # gender
            product_code,      # skuid
            status,            # stock_status
            original_price,    # original_price_gbp
            discount_price,    # discount_price_gbp
            "总库存"           # stock_name (固定值)
        )
        records.append(record)

    return records
