import pandas as pd
import os

# === 参数设置 ===
base_dir = r"D:/TB/taojingxiao/菜鸟excel"  # ⚠️ 修改为你的实际路径
product_file = os.path.join(base_dir, "货品.xlsx")
relation_file = os.path.join(base_dir, "商货品关系.xlsx")
custom_files = [os.path.join(base_dir, f"海关备案{i}.xlsx") for i in range(1, 8)]
output_file = os.path.join(base_dir, "filtered_货品导出.xlsx")

# === 读取货品.xlsx（所有字段作为文本）===
df_products = pd.read_excel(product_file, dtype=str)
df_products.fillna("", inplace=True)
df_products_full = df_products.copy()

# === 读取商货品关系，处理菜鸟货品ID ===
df_relation = pd.read_excel(relation_file, dtype=str)
df_relation.fillna("", inplace=True)
df_relation["菜鸟货品ID"] = df_relation["菜鸟货品ID"].str.replace(r"\*1$", "", regex=True)
related_ids = set(df_relation["菜鸟货品ID"])

# === 合并所有海关备案文件的货品ID ===
custom_ids = set()
for file in custom_files:
    if os.path.exists(file):
        df_custom = pd.read_excel(file, dtype=str)
        df_custom.fillna("", inplace=True)
        if "货品ID" in df_custom.columns:
            custom_ids.update(df_custom["货品ID"])

# === 增加标记列 ===
df_products_full["是否绑定关系"] = df_products_full["货品ID"].apply(lambda x: "是" if x in related_ids else "否")
df_products_full["是否海关备案"] = df_products_full["货品ID"].apply(lambda x: "是" if x in custom_ids else "否")

# === 排除货品名称包含“缺码联系客服”的记录 ===
df_products_filtered = df_products_full[~df_products_full["货品名称"].str.contains("缺码联系客服", na=False)]

# === 筛选未绑定 且 未备案的记录 ===
df_unbound_full = df_products_filtered[
    (df_products_filtered["是否绑定关系"] == "否") &
    (df_products_filtered["是否海关备案"] == "否")
]

# === 导出为 Excel（全部字段为文本）===
df_unbound_full.to_excel(output_file, index=False)

print(f"\n✅ 已导出结果：{output_file}")
