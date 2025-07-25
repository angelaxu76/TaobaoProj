import pandas as pd

# 文件路径
gei_file = r'D:\TB\Products\camper\document\GEI@sales_catalogue_export@250723051812@2528.xlsx'
output_file = r'D:\TB\Products\camper\document\duplicate_channel_ids.xlsx'

# 1. 读取 GEI Excel
gei_df = pd.read_excel(gei_file)

# 提取商品编码
gei_df['product_code'] = gei_df['sku名称'].astype(str).str.split('，').str[0].str.strip()

# 2. 分组统计，找出重复 channel ID 的商品
dup_df = (gei_df.groupby('product_code')['渠道产品id']
          .apply(lambda x: ', '.join(x.dropna().astype(str).unique()))
          .reset_index())

# 统计重复次数
dup_df['channel_id_count'] = dup_df['渠道产品id'].apply(lambda x: len(x.split(',')))

# 只保留重复的（count > 1）
dup_df = dup_df[dup_df['channel_id_count'] > 1]

# 按重复次数排序
dup_df = dup_df.sort_values(by='channel_id_count', ascending=False)

# 3. 保存结果
dup_df.to_excel(output_file, index=False)

print(f"✅ 找到重复商品编码数量: {len(dup_df)}")
print(f"📂 文件已保存: {output_file}")
