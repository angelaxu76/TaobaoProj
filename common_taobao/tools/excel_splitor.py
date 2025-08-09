import pandas as pd
import math
from pathlib import Path

# ======== 参数配置 ========
input_file = Path(r"D:\TB\Products\camper\repulibcation\camper_男款商品列表.xlsx")  # 输入文件路径
output_dir = Path(r"D:\split_excel")  # 输出目录
num_parts = 4  # 分成几份（整数）

# 创建输出目录
output_dir.mkdir(parents=True, exist_ok=True)

# 读取 Excel 并全部转成字符串
df = pd.read_excel(input_file, dtype=str)

# 计算每份的行数（不包含表头）
rows_per_part = math.ceil(len(df) / num_parts)

for i in range(num_parts):
    start_idx = i * rows_per_part
    end_idx = start_idx + rows_per_part
    part_df = df.iloc[start_idx:end_idx]

    # 确保再次全部是字符串（防止空值）
    part_df = part_df.fillna("").astype(str)

    # 构造输出文件名
    output_file = output_dir / f"{input_file.stem}_part{i + 1}.xlsx"

    # 写入 Excel，保留表头
    part_df.to_excel(output_file, index=False)

print(f"✅ 拆分完成，共 {num_parts} 份，所有数据已转为文本，保存在 {output_dir}")
