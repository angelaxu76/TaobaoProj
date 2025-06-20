from pathlib import Path

def format_txt(info: dict, filepath: Path):
    """
    将 info 字典写入统一格式的 TXT 文件
    """
    fields = [
        "Product Code",
        "Product Name",
        "Product Description",
        "Product Gender",
        "Product Color",
        "Product Price",
        "Adjusted Price",
        "Product Material",
        "Product Size",
        "Source URL"
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        for field in fields:
            value = info.get(field, "No Data")
            f.write(f"{field}: {value}\n")
