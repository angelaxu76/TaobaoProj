import pandas as pd

# === 配置部分 ===
input_file = r"D:\TB\taojingxiao\jingya\GEI.xlsx"
sku_column_name = "sku名称"
distribution_status_column = "铺货状态"
channel_product_id_column = "渠道产品id"

output_codes_file = r"D:\TB\taojingxiao\jingya\unique_productCodes.xlsx"
output_unpublished_file = r"D:\TB\taojingxiao\jingya\unpublished_products.xlsx"

# === 读取Excel ===
df = pd.read_excel(input_file)

# === 提取唯一商品编码 ===
def extract_product_code(sku_name):
    if pd.isna(sku_name):
        return None
    return str(sku_name).split("，")[0].strip()

df["商品编码"] = df[sku_column_name].apply(extract_product_code)
unique_codes = df["商品编码"].dropna().drop_duplicates().reset_index(drop=True)
pd.DataFrame({"商品编码": unique_codes}).to_excel(output_codes_file, index=False)

# === 筛选“未铺货”的行并导出 ===
unpublished_df = df[df[distribution_status_column] == "未铺货"]
unpublished_df[[channel_product_id_column, distribution_status_column]].to_excel(output_unpublished_file, index=False)

print(f"✅ 已导出唯一商品编码到：{output_codes_file}")
print(f"✅ 已导出未铺货商品到：{output_unpublished_file}")
