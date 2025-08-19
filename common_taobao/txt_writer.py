from pathlib import Path
from common_taobao.core.category_utils import infer_style_category  # ✅ 如果函数写在这里就引入
from common_taobao.core.size_normalizer import infer_gender_for_barbour


def format_txt(info: dict, filepath: Path, brand: str = None):
    # ✅ 兜底推断 Style Category

    if (brand or info.get("Brand")) == "Barbour":
        info["Product Gender"] = infer_gender_for_barbour(
            product_code=info.get("Product Code"),
            title=info.get("Product Name"),
            description=info.get("Product Description"),
            given_gender=info.get("Product Gender"),
        ) or info.get("Product Gender") or "男款"

    # 类目智能化（你上一条已加好）
    if not info.get("Style Category"):
        info["Style Category"] = infer_style_category(
            desc=info.get("Product Description", ""),
            product_name=info.get("Product Name", ""),
            product_code=info.get("Product Code", ""),
            brand=(brand or info.get("Brand") or "")
        )

    if not info.get("Style Category"):
        desc  = info.get("Product Description", "")
        name  = info.get("Product Name", "")
        code  = info.get("Product Code", "")
        info["Style Category"] = infer_style_category(
            desc=desc,
            product_name=name,
            product_code=code,
            brand=(brand or info.get("Brand") or "")
        )

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
    write_line("Style Category", info.get("Style Category"))
    write_line("Feature", info.get("Feature"))

    # ✅ 写入 Product Size：通用格式（Clarks, ECCO 等）
    if "SizeMap" in info:
        size_str = ";".join(f"{size}:{status}" for size, status in info["SizeMap"].items())
        lines.append(f"Product Size: {size_str}")
    elif "Product Size" in info:  # fallback
        lines.append(f"Product Size: {info['Product Size']}")

    # ✅ 写入 Product Size Detail（带库存和 EAN）
    if "SizeDetail" in info:
        detail_lines = []
        for size, detail in info["SizeDetail"].items():
            stock_count = detail.get("stock_count", 0)
            ean = detail.get("ean", "")
            detail_lines.append(f"{size}:{stock_count}:{ean}")
        lines.append("Product Size Detail: " + ";".join(detail_lines))

    write_line("Source URL", info.get("Source URL"))

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 写入 TXT: {filepath.name}")
