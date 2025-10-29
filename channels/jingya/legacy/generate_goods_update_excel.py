import pandas as pd
import os
import re
import psycopg2
from config import CAMPER  # ✅ 引入 camper 品牌配置
from pathlib import Path

# === 货品文件请放到 D:\TB\taofenxiao\goods 目录下===
# === 目录与路径 ===
base_dir = Path("D:/TB/taofenxiao/goods")
output_excel_path = base_dir / "更新后的货品导入.xlsx"
txt_dir = CAMPER["TXT_DIR"]
table_name = CAMPER["TABLE_NAME"]
pg_config = CAMPER["PGSQL_CONFIG"]

# === 自动查找“货品导出”开头的 Excel ===
excel_files = [f for f in os.listdir(base_dir) if f.startswith("货品导出") and f.endswith(".xlsx")]
if not excel_files:
    raise FileNotFoundError("❌ 未找到以 '货品导出' 开头的 Excel 文件")
excel_files.sort(reverse=True)
input_excel_path = base_dir / excel_files[0]


# === 修正后的：从数据库查找唯一的 EAN 条形码 ===
def get_ean_by_code_and_size(product_code, size):
    try:
        conn = psycopg2.connect(**pg_config)
        cur = conn.cursor()
        cur.execute(
            f"SELECT ean FROM {table_name} WHERE product_code = %s AND size = %s AND ean IS NOT NULL",
            (product_code, size)
        )
        result = cur.fetchone()
        return result[0] if result else ""
    except Exception as e:
        print(f"❌ 查询条形码失败: {e}")
        return ""
    finally:
        if 'conn' in locals():
            conn.close()


# === 解析 TXT 文件内容 ===
def parse_txt(file_path):
    info = {"Product Code": "", "Gender": "", "Product Description": ""}
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("Product Code:"):
                info["Product Code"] = line.split(":", 1)[1].strip()
            elif line.startswith("Gender:"):
                info["Gender"] = line.split(":", 1)[1].strip()
            elif line.startswith("Product Description:"):
                info["Product Description"] = line.split(":", 1)[1].strip()
    return info


# === 判断鞋款分类 ===
def get_style(desc):
    desc = desc.lower()
    if "boot" in desc:
        return "男靴" if "men" in desc else "女靴"
    elif "sandal" in desc:
        return "凉鞋"
    else:
        return "休闲鞋"


# === 标准字段定义 ===
required_columns = [
    "货品编码", "货品名称", "货品名称（英文）", "条形码", "吊牌价", "零售价", "成本价", "易碎品", "危险品",
    "温控要求", "效期管理", "有效期（天）", "临期预警（天）", "禁售天数（天）", "禁收天数（天）",
    "长", "宽", "高", "毛重", "净重", "长-运输单元", "宽-运输单元", "高-运输单元", "重量-运输单元", "包含电池"
]

# === 固定值字段 ===
fixed_values = {
    "长": 360,
    "宽": 160,
    "高": 120,
    "毛重": 1200,
    "净重": 1000
}

# === 主处理逻辑 ===

df = pd.read_excel(input_excel_path)
output_rows = []

for _, row in df.iterrows():
    raw_name = str(row.get("货品名称", ""))
    code = str(row.get("货品编码", ""))
    barcode = str(row.get("条形码", ""))

    if not raw_name.startswith("颜色分类"):
        continue

    match = re.search(r"颜色分类:([^;]+);尺码:(.+)", raw_name)
    if not match:
        continue
    product_code, size = match.groups()

    txt_path = txt_dir / f"{product_code}.txt"
    if not txt_path.exists():
        print(f"⚠️ 缺失 TXT 文件: {txt_path.name}")
        continue

    info = parse_txt(txt_path)
    gender = info.get("Gender", "")
    desc = info.get("Product Description", "")
    style = get_style(desc)
    gender_label = "男鞋" if "男" in gender else "女鞋"
    new_name = f"camper看步休闲{gender_label}{style}{product_code}尺码{size}"

    # 获取该货品（编码+尺码）的唯一条形码
    ean = get_ean_by_code_and_size(product_code, size)

    final_barcode = barcode
    # 拼接两个条形码（淘宝已有 + 数据库查询到的ean）
    if ean and ean not in barcode:
        final_barcode = f"{barcode}#{ean}" if barcode else ean
    else:
        final_barcode = barcode

    # 构造行数据
    row_data = {
        "货品编码": code,
        "货品名称": new_name,
        "货品名称（英文）": "",
        "条形码": final_barcode,
        "吊牌价": "", "零售价": "", "成本价": "",
        "易碎品": "", "危险品": "", "温控要求": "",
        "效期管理": "", "有效期（天）": "", "临期预警（天）": "",
        "禁售天数（天）": "", "禁收天数（天）": "",
        "长-运输单元": "", "宽-运输单元": "", "高-运输单元": "", "重量-运输单元": "",
        "包含电池": ""
    }

    row_data.update(fixed_values)  # 注入 长宽高毛重净重
    output_rows.append(row_data)

# === 写入多个分组 Excel（每组最多500条） ===
group_size = 500
total = len(output_rows)
if total == 0:
    print("⚠️ 没有可导出的记录")
else:
    for i in range(0, total, group_size):
        group_rows = output_rows[i:i + group_size]
        output_df = pd.DataFrame(group_rows, columns=required_columns)
        group_index = i // group_size + 1
        group_filename = base_dir / f"更新后的货品导入_第{group_index}组.xlsx"
        output_df.to_excel(group_filename, sheet_name="商品信息", index=False)
        print(f"✅ 已生成文件：{group_filename}")
