import pandas as pd
import glob
import os
import re

# === 配置 ===
input_folder = r"D:\TB\brandresearch\品牌大全\dest"  # Excel文件目录
output_file = r"D:\TB\brandresearch\品牌大全\brand_summary.xlsx"


# === 数据清洗函数 ===
def parse_value(val):
    if pd.isna(val) or val == '':
        return 0
    val = str(val).strip().split("\n")[0]  # 取第一段（去掉换行后面的内容）
    val = val.replace(",", "").replace(" ", "")

    # 区间处理
    if "-" in val or "–" in val or "~" in val:
        parts = re.split(r'[-–~]', val)
        try:
            nums = [parse_value(p) for p in parts]
            return sum(nums) / len(nums)
        except:
            return 0

    # 百分比处理
    if "%" in val:
        val = val.replace("%", "")
        return float(val) / 100

    # 处理“万”
    if "万" in val:
        val = val.replace("万", "")
        try:
            return float(val) * 10000
        except:
            return 0

    try:
        return float(val)
    except:
        return 0


# === 汇总结果列表 ===
summary_data = []

# 遍历文件夹中的所有Excel文件
for file_path in glob.glob(os.path.join(input_folder, "*.xlsx")):
    brand_name = os.path.basename(file_path).replace(".xlsx", "")
    try:
        df = pd.read_excel(file_path)

        # 确认列名
        required_cols = ["搜索人气", "需求供给比", "支付买家数", "支付转化率"]
        if not all(col in df.columns for col in required_cols):
            print(f"⚠️ 文件 {brand_name} 缺少必要列，跳过")
            continue

        # 清洗数据
        for col in required_cols:
            df[col] = df[col].apply(parse_value)

        # 聚合
        total_search = df["搜索人气"].sum()
        total_buyers = df["支付买家数"].sum()
        avg_supply = df["需求供给比"].mean()
        avg_conversion = df["支付转化率"].mean()

        summary_data.append({
            "品牌": brand_name,
            "搜索人气": total_search,
            "支付买家数": total_buyers,
            "平均需求供给比": avg_supply,
            "平均转化率": avg_conversion
        })

    except Exception as e:
        print(f"❌ 处理文件 {brand_name} 出错: {e}")

# === 汇总成DataFrame ===
summary_df = pd.DataFrame(summary_data)

# === 标准化处理（用于评分） ===
for col in ["搜索人气", "支付买家数", "平均需求供给比", "平均转化率"]:
    max_val = summary_df[col].max()
    min_val = summary_df[col].min()
    summary_df[f"{col}_norm"] = (summary_df[col] - min_val) / (max_val - min_val)

# === 计算综合评分 ===
summary_df["综合评分"] = (
        summary_df["平均需求供给比_norm"] * 0.5 +
        summary_df["平均转化率_norm"] * 0.2 +
        summary_df["支付买家数_norm"] * 0.2 +
        summary_df["搜索人气_norm"] * 0.1
)

# 排序
summary_df = summary_df.sort_values(by="综合评分", ascending=False)

# === 保存到Excel ===
summary_df.to_excel(output_file, index=False)
print(f"✅ 品牌汇总文件已生成: {output_file}")
