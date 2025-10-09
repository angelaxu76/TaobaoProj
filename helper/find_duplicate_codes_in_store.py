import pandas as pd
from pathlib import Path
from collections import defaultdict

def find_duplicate_product_codes_in_store(store_folder: Path):
    if not store_folder.exists():
        print(f"❌ 店铺文件夹不存在: {store_folder}")
        return

    code_map = defaultdict(set)
    matched_file_count = 0

    # 遍历所有 Excel 文件
    for file in store_folder.glob("*.xls*"):
        if file.name.startswith("~$"):
            continue
        try:
            df = pd.read_excel(file, dtype=str)
            if not {"商家编码", "宝贝ID"}.issubset(df.columns):
                continue  # 跳过非宝贝信息表
            matched_file_count += 1
            print(f"📂 解析文件: {file.name}")

            df = df.dropna(subset=["商家编码", "宝贝ID"])
            for _, row in df.iterrows():
                code = str(row["商家编码"]).strip()
                item_id = str(row["宝贝ID"]).strip()
                code_map[code].add(item_id)
        except Exception as e:
            print(f"⚠️ 读取失败: {file.name} - {e}")

    if matched_file_count == 0:
        print(f"⚠️ 未找到包含宝贝ID的 Excel 文件")
        return

    # 查找重复项
    print("\n🔍 查找商家编码重复的记录...\n")
    duplicates = {code: ids for code, ids in code_map.items() if len(ids) > 1}

    if not duplicates:
        print("✅ 没有发现商家编码重复对应多个宝贝ID的情况。")
    else:
        print("❗ 以下商家编码重复对应多个宝贝ID：\n")
        for code, ids in duplicates.items():
            print(f"商家编码: {code}")
            for item_id in ids:
                print(f"  → 宝贝ID: {item_id}")
            print("-" * 30)

# ✅ 示例调用
if __name__ == "__main__":
    store_path = Path(r"D:\TB\Products\ECCO\document\store\英国伦敦代购2015")  # 替换为实际路径
    #store_path = Path(r"D:\TB\Products\camper_global\document\store\英国伦敦代购2015")  # 替换为实际路径
    find_duplicate_product_codes_in_store(store_path)
