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

def export_discount_excel(txt_dir, brand, output_excel):
    """
    扫描 TXT 文件并导出打折价 Excel（无打折价时使用当前价）
    参数:
        txt_dir: TXT 目录路径
        brand: 品牌名
        output_excel: 输出 Excel 文件路径
    """
    txt_dir = Path(txt_dir)
    records = []
    for file in txt_dir.glob("*.txt"):
        try:
            data = parse_txt(file)
            code = data.get("Product Code")
            price = data.get("Actual Price", "").replace("£", "").strip()
            was_price = data.get("Original Price", "").replace("£", "").strip()
            name = data.get("Product Name", "")
            color = data.get("Color", "")

            # 价格优先使用折扣价（如果原价比实际价格高）
            try:
                final_price = float(price)
                if was_price.lower() != "no data":
                    was_val = float(was_price)
                    if was_val > final_price:
                        price = final_price
            except:
                price = 0.0

            records.append({
                "品牌": brand,
                "商品编码": code,
                "价格": price,
                "商品名称": name,
                "颜色": color,
            })
        except Exception as e:
            print(f"❌ 错误处理 {file.name}: {e}")

    df = pd.DataFrame(records)
    df.to_excel(output_excel, index=False)
    print(f"✅ 导出成功: {output_excel}")