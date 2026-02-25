def extract_product_info(txt_file) -> dict:
    """
    从商品 TXT 文件中提取字段
    支持字段: Product Name, Product Description, Upper Material, AdjustedPrice, Price, gender
    """
    info = {}
    if not txt_file.exists():
        return info

    try:
        with open(txt_file, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    key, val = line.strip().split(":", 1)
                    info[key.strip()] = val.strip()
    except:
        return {}

    return info


