# -*- coding: utf-8 -*-
"""
检查 Excel 中 SKU 名称是否有重复，并输出到 TXT 文件

用法：
python check_duplicate_sku.py --input "input.xlsx" --output "duplicates.txt"

默认参数可在代码开头修改。
"""

import argparse
import pandas as pd
from pathlib import Path

# ======================== 默认参数（可修改） ========================
DEFAULT_INPUT = r"D:\TB\Products\camper\document\GEI@sales_catalogue_export@250912041305@8078.xlsx"
DEFAULT_OUTPUT = r"D:\TB\Products\camper\document\duplicate_skus.txt"
SKU_COLUMN = "sku名称"   # Excel 中的列名
# ================================================================

def check_duplicates(input_file: str, output_file: str, sku_column: str = SKU_COLUMN):
    """检查 Excel 中 SKU 是否有重复，并输出到 TXT"""
    df = pd.read_excel(input_file, dtype=str)

    if sku_column not in df.columns:
        raise ValueError(f"❌ 未找到列 '{sku_column}'，Excel 列名有: {list(df.columns)}")

    # 找出重复值
    duplicates = df[df.duplicated(subset=[sku_column], keep=False)]
    dup_values = duplicates[sku_column].dropna().unique()

    with open(output_file, "w", encoding="utf-8") as f:
        if len(dup_values) == 0:
            f.write("✅ 未发现重复的 SKU 名称\n")
            print("✅ 未发现重复的 SKU 名称")
        else:
            f.write("⚠ 发现重复 SKU 名称:\n")
            for val in dup_values:
                f.write(f"{val}\n")
            print(f"⚠ 已输出 {len(dup_values)} 个重复 SKU 到 {output_file}")


def main():
    parser = argparse.ArgumentParser(description="检查 Excel 中 SKU 是否有重复")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT, help="输入 Excel 文件路径")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="输出 TXT 文件路径")
    args = parser.parse_args()

    check_duplicates(args.input, args.output)


if __name__ == "__main__":
    main()
