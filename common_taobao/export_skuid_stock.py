import os
import pandas as pd
from pathlib import Path

def parse_txt(file_path):
    info = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if ':' in line:
                key, val = line.strip().split(":", 1)
                info[key.strip()] = val.strip()
    return info

def export_stock_excel(txt_dir, brand, store_id, output_excel):
    """
    导出每个商品的库存信息（品牌 + 店铺 ID）
    参数:
        txt_dir: TXT 文件夹路径
        brand: 品牌名
        store_id: 淘宝店铺ID
        output_excel: 输出Excel路径
    """
    txt_dir = Path(txt_dir)
    records = []
    for file in txt_dir.glob("*.txt"):
        try:
            data = parse_txt(file)
            code = data.get("Product Code")
            name = data.get("Product Name", "")
            gender = data.get("Product Gender", "")
            color = data.get("Color", "")
            sizes = data.get("Size Stock (EU)", "")
            for size_status in sizes.split(";"):
                if ":" in size_status:
                    size, status = size_status.split(":")
                    size = size.strip()
                    stock = 3 if "有货" in status else 0
                    records.append({
                        "品牌": brand,
                        "商品编码": code,
                        "商品名称": name,
                        "性别": gender,
                        "颜色": color,
                        "尺码(EU)": size,
                        "库存": stock,
                        "店铺ID": store_id
                    })
        except Exception as e:
            print(f"❌ 错误处理 {file.name}: {e}")

    df = pd.DataFrame(records)
    df.to_excel(output_excel, index=False)
    print(f"✅ 导出成功: {output_excel}")