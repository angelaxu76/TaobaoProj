import pandas as pd
import re

# ========== 参数区 ==========
INPUT_TXT = r"D:\temp\channel_products.txt"   # 输入TXT路径
OUTPUT_XLSX = r"D:\temp\channel_products.xlsx" # 输出Excel路径
# ============================

def parse_txt_to_excel(input_txt, output_xlsx):
    """解析渠道产品TXT并导出Excel"""
    with open(input_txt, "r", encoding="utf-8") as f:
        raw_data = f.read()

    # 正则匹配每 10 个字段为一行
    pattern = re.compile(
        r"(.+?)\n"     # 渠道产品名称
        r"(\d+)\n"     # 渠道产品ID
        r"(.+?)\n"     # 货品ID
        r"(.+?)\n"     # 类目
        r"(.+?)\n"     # 供应商名称
        r"(.+?)\n"     # 宝贝关联状态
        r"([\d\.]+)\n" # 价格
        r"(\d+)\n"     # 库存
        r"(.+?)\n"     # 库存类型
        r"(.+?)\n",    # 操作
        re.S
    )

    rows = [list(match) for match in pattern.findall(raw_data)]

    columns = [
        "渠道产品名称","渠道产品ID","货品ID","类目","供应商名称",
        "宝贝关联状态","价格(元)","库存","库存类型","操作"
    ]
    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(output_xlsx, index=False)
    print(f"✅ 已导出 Excel: {output_xlsx} | 共 {len(df)} 条记录")

def main():
    parse_txt_to_excel(INPUT_TXT, OUTPUT_XLSX)

if __name__ == "__main__":
    main()
