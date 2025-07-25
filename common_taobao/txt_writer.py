from pathlib import Path

def format_txt(info: dict, filepath: Path, brand: str = None):
    lines = []

    def write_line(key, val):
        if val:
            lines.append(f"{key}: {val}")

    write_line("Product Code", info.get("Product Code"))
    write_line("Product Name", info.get("Product Name"))
    write_line("Product Description", info.get("Product Description"))
    write_line("Product Gender", info.get("Product Gender"))
    write_line("Product Color", info.get("Product Color"))
    write_line("Product Price", info.get("Product Price"))
    write_line("Adjusted Price", info.get("Adjusted Price"))
    write_line("Product Material", info.get("Product Material"))




    # ✅ 写入 Product Size：通用格式（Clarks, ECCO 等）
    if "SizeMap" in info:
        size_str = ";".join(f"{size}:{status}" for size, status in info["SizeMap"].items())
        lines.append(f"Product Size: {size_str}")
    elif "Product Size" in info:  # fallback
        lines.append(f"Product Size: {info['Product Size']}")

    # ✅ Camper 专用格式（带库存数字和 EAN）
    if brand == "camper" and "SizeDetail" in info:
        detail_lines = []
        for size, detail in info["SizeDetail"].items():
            stock_count = detail.get("stock_count", 0)
            ean = detail.get("ean", "")
            detail_lines.append(f"{size}:{stock_count}:{ean}")
        lines.append("Product Size Detail: " + ";".join(detail_lines))

    write_line("Source URL", info.get("Source URL"))

    # 写入文件
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入 TXT: {filepath.name}")
