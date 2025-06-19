import os
import pandas as pd
from pathlib import Path

def generate_publish_report(txt_dir, brand, published_codes, output_excel):
    """
    生成发布状态报告，包括是否已发布、库存情况等
    参数:
        txt_dir: TXT 目录路径
        brand: 品牌名
        published_codes: 已发布商品编码列表或集合
        output_excel: 输出 Excel 路径
    """
    txt_dir = Path(txt_dir)
    rows = []

    for file in txt_dir.glob("*.txt"):
        try:
            data = {}
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.strip().split(":", 1)
                        data[key.strip()] = val.strip()

            code = data.get("Product Code")
            name = data.get("Product Name", "")
            gender = data.get("Product Gender", "")
            sizes = data.get("Size Stock (EU)", "")

            size_list = sizes.split(";")
            in_stock_sizes = [s for s in size_list if "有货" in s]
            publish_flag = "✅已发布" if code in published_codes else "❌未发布"

            rows.append({
                "品牌": brand,
                "商品编码": code,
                "商品名称": name,
                "性别": gender,
                "有货尺码数": len(in_stock_sizes),
                "发布状态": publish_flag,
            })

        except Exception as e:
            print(f"❌ 错误处理 {file.name}: {e}")

    df = pd.DataFrame(rows)
    df.sort_values(by=["发布状态", "有货尺码数"], ascending=[True, False], inplace=True)
    df.to_excel(output_excel, index=False)
    print(f"✅ 发布报告导出成功：{output_excel}")