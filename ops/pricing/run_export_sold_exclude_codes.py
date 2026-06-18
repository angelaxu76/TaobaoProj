"""
从鲸芽订单 Excel 中提取各品牌已售商品编码，
每个品牌生成一个单列 Excel（exclude 白名单），
用于价格修改时跳过这些商品（15天保价承诺期内不改价）。

商品编码解析方式：从"货品名称"提取"尺码"前最后一段 ASCII，例如：
  clarks其乐女鞋凉鞋26181653尺码40   → 26181653
  camper看步女鞋凉鞋K201486-020尺码39 → K201486-020
  ecco爱步women休闲鞋21280359390尺码39 → 21280359390
  geox健乐士女鞋休闲鞋D657NA000TUC9999尺码37.5 → D657NA000TUC9999
  Barbour男装外套MCA1019GY51尺码36   → MCA1019GY51

修改下方参数后直接运行。
"""

import os
import re
import glob
import pandas as pd

# ==================== 参数 ====================
INPUT_DIR    = r"C:/Users/angel/Downloads"       # 订单 Excel 所在目录
SHARED_ROOT  = r"E:/shared/GEI_SHARED"          # 共享目录根路径
# ==============================================

# 货品名称里"尺码"前最后一段连续 ASCII（含短横）即为商品编码
_CODE_RE = re.compile(r"[A-Za-z0-9\-]+(?=尺码)")


def _extract_code(name: str) -> str:
    matches = _CODE_RE.findall(name)
    return matches[-1] if matches else ""


def _detect_brand(name: str) -> str:
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
    if "reiss" in lower:
        return "reiss"
    if "marks" in lower or "m&s" in lower:
        return "marksandspencer"
    return ""


def _find_column(df: pd.DataFrame, candidates: list) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _process_file(filepath: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(filepath, sheet_name=0, dtype=str)
    except Exception as e:
        print(f"[WARN] 无法读取 {os.path.basename(filepath)}: {e}")
        return pd.DataFrame(columns=["商品编码", "brand"])

    name_col = _find_column(df, ["货品名称", "货品名", "商品名称", "宝贝名称", "标题"])
    if not name_col:
        print(f"[WARN] {os.path.basename(filepath)} 找不到货品名称列，已跳过")
        return pd.DataFrame(columns=["商品编码", "brand"])

    sub = df[[name_col]].copy()
    sub.rename(columns={name_col: "货品名称"}, inplace=True)
    sub = sub[sub["货品名称"].notna()]

    sub["brand"] = sub["货品名称"].apply(_detect_brand)
    sub["商品编码"] = sub["货品名称"].apply(_extract_code)

    # 丢弃未识别品牌或无法提取编码的行
    sub = sub[(sub["brand"] != "") & (sub["商品编码"] != "")]

    print(f"[INFO] {os.path.basename(filepath)}: {len(sub)} 行有效数据")
    return sub[["商品编码", "brand"]]


def export_sold_exclude_codes(input_dir: str, shared_root: str):
    files = (
        glob.glob(os.path.join(input_dir, "*.xlsx")) +
        glob.glob(os.path.join(input_dir, "*.xls"))
    )
    if not files:
        print(f"[ERROR] 没找到 Excel 文件: {input_dir}")
        return

    print(f"[INFO] 找到 {len(files)} 个文件")

    rows = []
    for f in files:
        df = _process_file(f)
        if not df.empty:
            rows.append(df)

    if not rows:
        print("[WARN] 没有任何数据被解析")
        return

    final = pd.concat(rows, ignore_index=True)

    for brand, group in final.groupby("brand"):
        brand_dir = os.path.join(shared_root, brand)
        if not os.path.isdir(brand_dir):
            print(f"[WARN] 目录不存在，已跳过: {brand_dir}")
            continue
        codes = (
            group["商品编码"]
            .drop_duplicates()
            .sort_values()
            .reset_index(drop=True)
            .to_frame(name="商品编码")
        )
        out_path = os.path.join(brand_dir, "exclude.xlsx")
        codes.to_excel(out_path, index=False, sheet_name="Sheet1")
        print(f"[DONE] {brand}: {len(codes)} 个唯一编码 → {out_path}")


if __name__ == "__main__":
    export_sold_exclude_codes(INPUT_DIR, SHARED_ROOT)
