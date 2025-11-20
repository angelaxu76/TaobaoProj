import pandas as pd

file_path = r"C:\Users\martin\Downloads\GEI@sales_catalogue_export@251120080908@8834.xlsx"

# 尝试读取 Excel 文件
try:
    df = pd.read_excel(file_path)
    print("✅ 成功读取 Excel 文件")
except Exception as e:
    print("❌ 读取 Excel 文件失败:", e)
    exit()

# === 修改为实际的 SKU 列名 ===
sku_col = "sku名称"  # 例如 "SKU", "SKU Name"，你可以运行后检查列名

# 检查列名是否存在
if sku_col not in df.columns:
    print(f"⚠️ 列 '{sku_col}' 不存在。以下是所有可用列名：")
    print(df.columns.tolist())
    exit()

# 查找重复的 SKU 值
dups = df[df.duplicated(subset=[sku_col], keep=False)]

if dups.empty:
    print("✅ 没有重复的 SKU。")
else:
    output_file = r"C:\Users\martin\Downloads\重复SKU.xlsx"
    dups.to_excel(output_file, index=False)
    print(f"⚠️ 共发现 {dups.shape[0]} 行重复记录，已导出至：{output_file}")
