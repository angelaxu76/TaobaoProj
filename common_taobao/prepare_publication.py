import os
import shutil
from pathlib import Path
import pandas as pd

def parse_txt(file_path):
    info = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if ':' in line:
                key, val = line.strip().split(":", 1)
                info[key.strip()] = val.strip()
    return info

def prepare_products(txt_dir, image_dir, output_dir, brand):
    """
    准备发布商品：
    - 按性别将商品信息导出为 Excel
    - 将图片复制到 output_dir/brand/images 下
    参数:
        txt_dir: TXT 文件目录
        image_dir: 原始图片目录
        output_dir: 输出路径目录
        brand: 品牌名
    """
    txt_dir = Path(txt_dir)
    image_dir = Path(image_dir)
    output_dir = Path(output_dir)
    excel_out = output_dir / brand
    image_out = excel_out / "images"
    image_out.mkdir(parents=True, exist_ok=True)

    men_data, women_data, kids_data = [], [], []

    for file in txt_dir.glob("*.txt"):
        try:
            data = parse_txt(file)
            gender = data.get("Product Gender", "").lower()
            entry = {
                "商品编码": data.get("Product Code"),
                "商品名称": data.get("Product Name"),
                "价格": data.get("Actual Price"),
                "颜色": data.get("Color"),
            }
            if gender == "men":
                men_data.append(entry)
            elif gender == "women":
                women_data.append(entry)
            elif gender == "kids":
                kids_data.append(entry)

            # 图片复制
            code = data.get("Product Code")
            for i in range(1, 10):  # 最多复制9张图
                img_name = f"{code}_{i}.jpg"
                src = image_dir / img_name
                dst = image_out / img_name
                if src.exists():
                    shutil.copyfile(src, dst)

        except Exception as e:
            print(f"❌ 错误处理 {file.name}: {e}")

    if men_data:
        pd.DataFrame(men_data).to_excel(excel_out / "men待发布商品.xlsx", index=False)
    if women_data:
        pd.DataFrame(women_data).to_excel(excel_out / "women待发布商品.xlsx", index=False)
    if kids_data:
        pd.DataFrame(kids_data).to_excel(excel_out / "kids待发布商品.xlsx", index=False)

    print(f"✅ 发布准备完成：输出路径 → {excel_out}")