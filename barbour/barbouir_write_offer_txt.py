from pathlib import Path
from datetime import datetime

# common_taobao/txt_writer.py

from pathlib import Path
from datetime import datetime

def write_barbour_product_txt(info: dict, filepath: Path, brand=""):
    lines = [
        f"Product Name: {info.get('Product Name', '')}",
        f"Product Color: {info.get('Product Color', '')}",
        f"Product Color Code: {info.get('Product Code', '') or info.get('Product Color Code', '')}",
        f"Site Name: {info.get('Site Name', '')}",
        f"Product URL: {info.get('Source URL', '') or info.get('Product URL', '')}",
        "Offer List:",
    ]

    # 处理尺码列表
    size_map = info.get("SizeMap", {})
    if size_map:
        for size, stock in size_map.items():
            lines.append(f"  {size}|{info.get('Product Price', '0')}|{stock}|{stock == '有货'}")
    elif "Offers" in info:
        for offer in info["Offers"]:
            uk_size, price, stock_status, can_order = offer
            lines.append(f"  {uk_size}|{price:.2f}|{stock_status}|{can_order}")

    # Barbour 官网才写入的附加字段
    if brand.lower() == "barbour":
        extra_fields = [
            "Product Description", "Product Gender",
            "Adjusted Price", "Product Material", "Feature"
        ]
        for field in extra_fields:
            value = info.get(field, "").strip()
            if value:
                lines.append(f"{field}: {value}")

    lines.append(f"Updated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def write_supplier_offer_txt(data: dict, filepath: Path):
    lines = [
        f"Product Name: {data.get('Product Name', '')}",
        f"Product Color: {data.get('Product Color', '')}",
        f"Product Color Code: {data.get('Product Color Code', '')}",
        f"Site Name: {data.get('Site Name', '')}",
        f"Product URL: {data.get('Product URL', '')}",
        "Offer List:",
    ]

    for offer in data.get("Offers", []):
        uk_size, price, stock_status, can_order = offer
        lines.append(f"  {uk_size}|{price:.2f}|{stock_status}|{can_order}")

    lines.append(f"Updated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 附加字段写入
    optional_fields = [
        "Product Description", "Product Gender", "Product Price",
        "Adjusted Price", "Product Material", "Feature"
    ]
    for field in optional_fields:
        value = data.get(field)
        if value and field not in data.get("Product Name", ""):  # 避免重复
            lines.append(f"{field}: {value}")

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入报价信息: {filepath.name}")
