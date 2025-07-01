import pandas as pd
from pathlib import Path
import re
from config import PGSQL_CONFIG

# === 路径设置 ===
base_dir = Path("D:/TB/taofenxiao/goods")
product_file = list(base_dir.glob("货品导出*.xlsx"))[0]
relation_file = base_dir / "商货品关系导出.xlsx"
template_file = base_dir / "单个商品绑定上传模板.xlsx"  # 模板必须在相同目录

# === 读取模板列顺序 ===
template_df = pd.read_excel(template_file, sheet_name=0, dtype=str)
template_columns = list(template_df.columns)

# === 读取原始数据 ===
df_product = pd.read_excel(product_file, dtype=str)
df_relation = pd.read_excel(relation_file, dtype=str)

# === 提取绑定ID，去除末尾 *1
df_relation["菜鸟货品ID"] = df_relation["菜鸟货品ID"].str.replace(r"\*1$", "", regex=True)
bound_ids = df_relation["菜鸟货品ID"].dropna().unique()

# === 找出未绑定数据
unbound_df = df_product[~df_product["货品ID"].isin(bound_ids)].copy()
unbound_df["*菜鸟货品ID"] = unbound_df["货品ID"]
unbound_df["*商品名称"] = unbound_df["货品名称"]

# === 过滤不需要的商品（包含“调货”的、或不包含“camper”的）
filtered_df = unbound_df[
    ~unbound_df["*商品名称"].str.contains("调货", na=False) &
    unbound_df["*商品名称"].str.contains("camper", case=False, na=False)
].copy()

# === 解析“外部渠道商品ID”：编码 + 尺码（去除连接符）
def extract_channel_item_id(name: str) -> str:
    if not isinstance(name, str):
        return ""
    # 提取商品编码，格式支持数字/字母 + 5-6位数字 + [-_] + 3位数字
    code_match = re.search(r'([A-Z]?\d{5,6}[-_]\d{3})', name, re.IGNORECASE)
    # 提取尺码
    size_match = re.search(r'尺码?(\d+)', name)
    if code_match and size_match:
        code = code_match.group(1).replace("-", "").replace("_", "")
        size = size_match.group(1)
        return code + size
    return ""


filtered_df["*外部渠道商品ID"] = filtered_df["*商品名称"].apply(extract_channel_item_id)

# === 添加固定字段 ===
filtered_df["*销售渠道"] = "淘分销"
filtered_df["*渠道店铺ID"] = "2219163936872"
filtered_df["*发货模式"] = "直发"

# === 生成最终数据并按模板列顺序输出 ===
final_df = filtered_df.reindex(columns=template_columns)

# === 导出 Excel 文件 ===
output_file = base_dir / "未绑定商品绑定信息.xlsx"
with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    final_df.to_excel(writer, index=False, sheet_name="单个商品绑定")

print(f"✅ 已生成严格对齐模板格式的文件：{output_file}")
