from pathlib import Path

def write_offer_txt(filepath: Path, data: dict):
    lines = [
        f"Product Name: {data['Product Name']}",
        f"Product Color: {data['Product Color']}",
        f"Site Name: {data['Site Name']}",
        f"Product URL: {data['Product URL']}",
        f"Offer List:"
    ]
    for size, price, stock_status, can_order in data["Offers"]:
        lines.append(f"  {size}|{price:.2f}|{stock_status}|{str(can_order).upper()}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
