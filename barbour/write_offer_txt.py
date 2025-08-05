from pathlib import Path
from datetime import datetime

def write_offer_txt(data: dict, filepath: Path):
    """写入报价 TXT，保留旧模板格式，并加入 Product Color Code 字段"""
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

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"Updated At: {now}")

    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入报价信息: {filepath.name}")
