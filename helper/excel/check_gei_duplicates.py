import pandas as pd

from config import DOWNLOADS_DIR

# 自动查找 Downloads 下 GEI 开头的 Excel（忽略 Excel 打开时生成的 ~$ 临时文件）
candidates = sorted(
    (p for p in DOWNLOADS_DIR.glob("GEI*.xls*") if not p.name.startswith("~$")),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not candidates:
    print(f"❌ 在 {DOWNLOADS_DIR} 下未找到 GEI 开头的 Excel 文件")
    exit()
if len(candidates) > 1:
    print(f"⚠️ 找到 {len(candidates)} 个 GEI 文件，使用最新的一个：")
    for p in candidates:
        print("   ", p.name)
file_path = str(candidates[0])
print(f"📄 使用文件：{candidates[0].name}")

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
    output_file = str(DOWNLOADS_DIR / "重复SKU.xlsx")
    dups.to_excel(output_file, index=False)
    print(f"⚠️ 共发现 {dups.shape[0]} 行重复记录，已导出至：{output_file}")
