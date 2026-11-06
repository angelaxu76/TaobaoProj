import os
import re
import glob
import argparse
import pandas as pd

from cainiao.hscode_audit import hscode_issue
from cainiao.split_excel_by_brand import _detect_brand


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


def parse_code_from_goods_name(name: str) -> str:
    """
    从订单货品名称解析货号，提取不到返回 ""。支持：
      - camper看步男鞋靴子K300305-028尺码41
      - 颜色分类:K300305-028;尺码:41（也支持 颜色 / 主要颜色）
    """
    s = str(name or "")
    m = re.search(r"(?:主要颜色|颜色分类|颜色)\s*[:：]\s*([^;；]+)", s) or \
        re.search(r"([A-Za-z0-9-]+)\s*尺码", s)
    return m.group(1).strip() if m else ""


def detect_brand_from_goods_code(name: str) -> str:
    """名称和库存表都识别不出品牌时，按货号格式判断。"""
    code = parse_code_from_goods_name(name)
    brand = _detect_brand(code) if code else ""
    return "" if brand == "other" else brand


# 货品名称识别不出品牌时（如 "颜色分类:xxx;尺码:36"），用货品id 到各品牌表反查
BRAND_TABLES = {
    "camper": "camper_inventory",
    "ecco": "ecco_inventory",
    "clarks": "clarks_inventory",
    "geox": "geox_inventory",
    "barbour": "barbour_inventory",
}


def lookup_brands_by_item_ids(item_ids) -> dict:
    """
    批量按 channel_item_id 在各品牌库存表中查找，返回 {货品id: brand}。
    数据库不可用时返回空 dict，不中断流程。
    """
    item_ids = list({i for i in item_ids if i})
    if not item_ids:
        return {}

    try:
        import psycopg2
        from config import PGSQL_CONFIG
        conn = psycopg2.connect(**PGSQL_CONFIG)
    except Exception as e:
        print(f"[WARN] 无法连接数据库，跳过货品id反查品牌: {e}")
        return {}

    found = {}
    try:
        with conn.cursor() as cur:
            for brand, table in BRAND_TABLES.items():
                remaining = [i for i in item_ids if i not in found]
                if not remaining:
                    break
                try:
                    cur.execute(
                        f"SELECT DISTINCT channel_item_id FROM {table} WHERE channel_item_id = ANY(%s)",
                        (remaining,),
                    )
                    for (cid,) in cur.fetchall():
                        found[str(cid)] = brand
                except Exception as e:
                    conn.rollback()
                    print(f"[WARN] 查询 {table} 失败: {e}")
    finally:
        conn.close()

    return found


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
    - 返回 (DataFrame[货品id(文本), brand, 货品名称, 货品编码], issues, ignored_files)
    """
    empty = pd.DataFrame(columns=["货品id", "brand", "货品名称", "货品编码"])
    file_name = os.path.basename(filepath)

    try:
        df = pd.read_excel(filepath, sheet_name=0)
    except Exception as e:
        print(f"[WARN] 无法读取文件 {filepath}: {e}")
        return empty, [hscode_issue("", "", "读取订单", f"文件 {file_name} 无法读取：{e}")], []

    # 找列名（尽量兼容）
    product_id_col = find_column(df, ["货品id", "货品ID", "货品Id", "商品id", "商品ID"])
    product_name_col = find_column(df, ["货品名称", "货品名", "商品名称", "宝贝名称", "标题"])
    goods_sku_col = find_column(df, ["货品编码"])

    if not product_id_col or not product_name_col:
        print(f"[WARN] 文件 {file_name} 缺少 '货品id' 或 '货品名称' 列，已跳过。")
        return empty, [], [file_name]

    sub = df[[product_id_col, product_name_col]].copy()
    sub.rename(columns={product_id_col: "货品id", product_name_col: "货品名称"}, inplace=True)
    sub["货品编码"] = df[goods_sku_col].apply(normalize_product_id) if goods_sku_col else ""

    # 去掉空 id；有名称却没有 id 的行要记下来
    issues = [
        hscode_issue("", "", "读取订单", f"文件 {file_name} 中货品id为空：{name}")
        for name in sub.loc[sub["货品id"].isna() & sub["货品名称"].notna(), "货品名称"]
    ]
    sub = sub[sub["货品id"].notna()]

    # 识别品牌
    sub["brand"] = sub["货品名称"].apply(detect_brand_from_name)

    # 把货品id转成“文本”
    sub["货品id"] = sub["货品id"].apply(normalize_product_id)

    result = sub[["货品id", "brand", "货品名称", "货品编码"]].copy()

    print(f"[INFO] 文件 {file_name} 处理完成，行数: {len(result)}")
    return result, issues, []


# -----------------------------------------------------------
# ✅ 主函数：支持 pipeline 调用
# -----------------------------------------------------------
def extract_goods_brand_info(input_dir: str, shoes_output: str, barbour_output: str):
    """
    从 input_dir 中批量解析 Excel 文件，输出两个 Excel：
    - camper/ecco/clarks/geox --> shoes_output（按 brand 排序）
    - barbour --> barbour_output

    返回 (shoes_written, barbour_written, audit)：
    - shoes_written/barbour_written：对应文件本次是否实际生成，供调用方判断是否跳过后续步骤
    - audit：{"order_ids", "issues", "ignored_files"}，供 report_hscode_audit 核对
    """

    audit = {"order_ids": set(), "issues": [], "ignored_files": []}

    files = glob.glob(os.path.join(input_dir, "*.xlsx")) + \
            glob.glob(os.path.join(input_dir, "*.xls"))
    # Excel 打开文件时产生的 ~$ 临时文件不是订单
    files = [f for f in files if not os.path.basename(f).startswith("~$")]

    if not files:
        print(f"[ERROR] 没找到 Excel 文件: {input_dir}")
        return False, False, audit

    print(f"[INFO] 在目录 {input_dir} 中找到 {len(files)} 个文件。")

    all_results = []

    for f in files:
        df_res, file_issues, ignored = process_one_file(f)
        audit["issues"].extend(file_issues)
        audit["ignored_files"].extend(ignored)
        if not df_res.empty:
            all_results.append(df_res)

    if not all_results:
        print("[WARN] 没有任何数据被解析。")
        return False, False, audit

    final_df = pd.concat(all_results, ignore_index=True)

    # 再保险：这里再统一做一遍文本转换
    final_df["货品id"] = final_df["货品id"].apply(normalize_product_id)
    audit["order_ids"] = set(final_df["货品id"])

    # 名称里没有品牌的，用货品id 反查数据库
    unknown_mask = final_df["brand"] == ""
    if unknown_mask.any():
        id_brand = lookup_brands_by_item_ids(final_df.loc[unknown_mask, "货品id"])
        final_df.loc[unknown_mask, "brand"] = final_df.loc[unknown_mask, "货品id"].map(id_brand).fillna("")
        print(f"[INFO] 名称未识别品牌 {unknown_mask.sum()} 行，数据库反查命中 {len(id_brand)} 个货品id。")
        by_code_mask = final_df["brand"] == ""
        final_df.loc[by_code_mask, "brand"] = final_df.loc[by_code_mask, "货品名称"].map(detect_brand_from_goods_code)
        still_unknown = final_df.loc[final_df["brand"] == "", "货品id"].unique().tolist()
        if still_unknown:
            print(f"[WARN] 以下货品id 仍无法识别品牌，已跳过: {still_unknown}")
            audit["issues"].extend(
                hscode_issue(goods_id, "", "识别品牌", "订单名称和库存表都识别不出品牌")
                for goods_id in still_unknown
            )

    # 同一货品可能有多个订单，备案只需要一行
    final_df = final_df[final_df["brand"] != ""].drop_duplicates(subset="货品id")

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

    return not df_shoes.empty, not df_barbour.empty, audit


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
