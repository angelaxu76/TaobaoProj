import os
import glob
import argparse
import pandas as pd


def find_column(df, candidates):
    """
    在 DataFrame 中，根据候选列名列表找到第一个存在的列名。
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


def detect_brand_from_name(name: str) -> str:
    """
    根据货品名称识别品牌：
    - camper
    - ecco
    - clarks
    - geox
    - barbour
    """
    if not isinstance(name, str):
        return ""

    lower = name.lower()

    if "camper" in lower:
        return "camper"
    if "ecco" in lower:
        return "ecco"
    if "clarks" in lower:
        return "clarks"
    if "geox" in lower:
        return "geox"
    if "barbour" in lower:
        return "barbour"

    return ""


def normalize_product_id(val) -> str:
    """
    把货品id统一转成“文本”形式，避免：
    - 123.0
    - 科学计数法
    - NaN

    规则：
    - 浮点且是整数 -> 去小数，例如 123.0 -> "123"
    - 其他类型 -> 直接转 str
    - 空值 -> ""
    """
    if pd.isna(val):
        return ""

    # float 且为整数
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val)

    return str(val)


def process_one_file(filepath):
    """
    处理单个 Excel 文件：
    - 默认读取第一个 sheet
    - 找到“货品id”和“货品名称”列
    - 返回 DataFrame：货品id(文本), brand
    """
    try:
        df = pd.read_excel(filepath, sheet_name=0)
    except Exception as e:
        print(f"[WARN] 无法读取文件 {filepath}: {e}")
        return pd.DataFrame(columns=["货品id", "brand"])

    # 找列名（尽量兼容）
    product_id_col = find_column(df, ["货品id", "货品ID", "货品Id", "商品id", "商品ID"])
    product_name_col = find_column(df, ["货品名称", "货品名", "商品名称", "宝贝名称", "标题"])

    if not product_id_col or not product_name_col:
        print(f"[WARN] 文件 {os.path.basename(filepath)} 缺少 '货品id' 或 '货品名称' 列，已跳过。")
        return pd.DataFrame(columns=["货品id", "brand"])

    sub = df[[product_id_col, product_name_col]].copy()
    sub.rename(columns={product_id_col: "货品id", product_name_col: "货品名称"}, inplace=True)

    # 去掉空 id
    sub = sub[sub["货品id"].notna()]

    # 识别品牌
    sub["brand"] = sub["货品名称"].apply(detect_brand_from_name)

    # 把货品id转成“文本”
    sub["货品id"] = sub["货品id"].apply(normalize_product_id)

    result = sub[["货品id", "brand"]].copy()

    print(f"[INFO] 文件 {os.path.basename(filepath)} 处理完成，行数: {len(result)}")
    return result


# -----------------------------------------------------------
# ✅ 主函数：支持 pipeline 调用
# -----------------------------------------------------------
def extract_goods_brand_info(input_dir: str, shoes_output: str, barbour_output: str):
    """
    从 input_dir 中批量解析 Excel 文件，输出两个 Excel：
    - camper/ecco/clarks/geox --> shoes_output（按 brand 排序）
    - barbour --> barbour_output
    """

    files = glob.glob(os.path.join(input_dir, "*.xlsx")) + \
            glob.glob(os.path.join(input_dir, "*.xls"))

    if not files:
        print(f"[ERROR] 没找到 Excel 文件: {input_dir}")
        return

    print(f"[INFO] 在目录 {input_dir} 中找到 {len(files)} 个文件。")

    all_results = []

    for f in files:
        df_res = process_one_file(f)
        if not df_res.empty:
            all_results.append(df_res)

    if not all_results:
        print("[WARN] 没有任何数据被解析。")
        return

    final_df = pd.concat(all_results, ignore_index=True)
    final_df = final_df[final_df["brand"] != ""]

    # 再保险：这里再统一做一遍文本转换
    final_df["货品id"] = final_df["货品id"].apply(normalize_product_id)

    shoe_brands = {"camper", "ecco", "clarks", "geox"}

    df_shoes = final_df[final_df["brand"].isin(shoe_brands)].copy()
    df_barbour = final_df[final_df["brand"] == "barbour"].copy()

    # ✅ 按 brand 分类展示：简单做法是排序，让同品牌聚在一起
    if not df_shoes.empty:
        df_shoes.sort_values(by=["brand", "货品id"], inplace=True)

    if not df_barbour.empty:
        df_barbour.sort_values(by=["货品id"], inplace=True)

    # 输出 Excel
    if df_shoes.empty:
        print("[INFO] 没有鞋类品牌数据。")
    else:
        os.makedirs(os.path.dirname(shoes_output), exist_ok=True)
        df_shoes.to_excel(shoes_output, sheet_name="sheet1", index=False)
        print(f"[DONE] 鞋类导出 → {shoes_output}，行数: {len(df_shoes)}")

    if df_barbour.empty:
        print("[INFO] 没有 Barbour 数据。")
    else:
        os.makedirs(os.path.dirname(barbour_output), exist_ok=True)
        df_barbour.to_excel(barbour_output, sheet_name="sheet1", index=False)
        print(f"[DONE] Barbour 导出 → {barbour_output}，行数: {len(df_barbour)}")


# -----------------------------------------------------------
# CLI 调用（保持兼容）
# -----------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="从多个订单 Excel 中抽取货品id + 品牌，"
                    "将 camper/ecco/clarks/geox 导出到一个 Excel，barbour 单独导出。"
    )
    parser.add_argument("--input-dir", required=True, help="输入 Excel 所在目录")
    parser.add_argument("--shoes-output", required=True, help="鞋类品牌输出 Excel 路径")
    parser.add_argument("--barbour-output", required=True, help="Barbour 输出 Excel 路径")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    extract_goods_brand_info(args.input_dir, args.shoes_output, args.barbour_output)
