import pandas as pd
import os
import re
import psycopg2
from pathlib import Path
from config import BRAND_CONFIG

# ======================= ✅【参数配置区】=======================
BRAND = "camper"  # 👈 品牌名（必须是 config.py 中 BRAND_CONFIG 的 key）
GOODS_DIR = Path("D:/TB/taofenxiao/goods")  # 👈 Excel 文件所在目录（自动查找以“货品导出”开头的文件）
GROUP_SIZE = 500  # 👈 每个输出 Excel 的最大记录数
# ===============================================================


def export_goods_excel(brand: str, goods_dir: Path, group_size: int = 500):
    config = BRAND_CONFIG[brand]
    txt_dir = config["TXT_DIR"]
    table_name = config["TABLE_NAME"]
    pg_config = config["PGSQL_CONFIG"]

    # 自动查找“货品导出”开头的 Excel
    excel_files = [f for f in os.listdir(goods_dir) if f.startswith("货品导出") and f.endswith(".xlsx")]
    if not excel_files:
        raise FileNotFoundError("❌ 未找到以 '货品导出' 开头的 Excel 文件")
    excel_files.sort(reverse=True)
    input_excel_path = goods_dir / excel_files[0]

    # 查询唯一条形码
    def get_ean(product_code, size):
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

    def get_style(desc):
        desc = desc.lower()
        if "boot" in desc:
            return "男靴" if "men" in desc else "女靴"
        elif "sandal" in desc:
            return "凉鞋"
        else:
            return "休闲鞋"

    required_columns = [
        "货品编码", "货品名称", "货品名称（英文）", "条形码", "吊牌价", "零售价", "成本价", "易碎品", "危险品",
        "温控要求", "效期管理", "有效期（天）", "临期预警（天）", "禁售天数（天）", "禁收天数（天）",
        "长", "宽", "高", "毛重", "净重", "长-运输单元", "宽-运输单元", "高-运输单元", "重量-运输单元", "包含电池"
    ]
    fixed_values = {
        "长": 360, "宽": 160, "高": 120,
        "毛重": 1200, "净重": 1000
    }

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
        new_name = f"{brand}看步休闲{gender_label}{style}{product_code}尺码{size}"

        ean = get_ean(product_code, size)
        final_barcode = f"{barcode}#{ean}" if ean and ean not in barcode else barcode

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

        row_data.update(fixed_values)
        output_rows.append(row_data)

    if not output_rows:
        print("⚠️ 没有可导出的记录")
        return

    for i in range(0, len(output_rows), group_size):
        group_rows = output_rows[i:i + group_size]
        output_df = pd.DataFrame(group_rows, columns=required_columns)
        group_index = i // group_size + 1
        output_file = goods_dir / f"更新后的货品导入_第{group_index}组.xlsx"
        output_df.to_excel(output_file, sheet_name="商品信息", index=False)
        print(f"✅ 已生成文件：{output_file}")


# === ✅ 若作为脚本运行 ===
if __name__ == "__main__":
    export_goods_excel(BRAND, GOODS_DIR, GROUP_SIZE)
