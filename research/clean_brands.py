input_file = r"D:\TB\brandresearch\BRAND.txt"      # 修改为你的文件路径
output_file = r"D:\TB\brandresearch\cleaned_brands.txt"

brands = set()

with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        # 跳过空行和无意义的条目
        if not line or len(line) == 1:  # 去掉单个字母
            continue
        # 去掉"("之后的说明，例如 "adidas (All)" → "adidas"
        line = line.split("(")[0].strip()
        # 标准化大小写
        line = line.title()
        brands.add(line)

# 排序
cleaned_list = sorted(brands)

# 保存结果
with open(output_file, "w", encoding="utf-8") as f:
    for brand in cleaned_list:
        f.write(brand + "\n")

print(f"✅ 处理完成，共 {len(cleaned_list)} 个品牌，结果保存在: {output_file}")
