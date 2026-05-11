import re
import pandas as pd
from pathlib import Path

# 包含 "颜色分类:CODE;尺码:XX" 格式数据的列名
PRODUCT_NAME_COL = "货品名称"

# 输入文件的 sheet 名称（默认 "file"，改成 None 则读第一个 sheet）
INPUT_SHEET_NAME = "file"


def _extract_code(product_name: str) -> str | None:
    """
    从以下两种格式中提取编码：
      - '颜色分类:CODE;尺码:XX'  （鞋类：ecco / clarks / camper）
      - '颜色:CODE;尺码:XX'      （服装类：barbour 衣服）
    不以上述前缀开头时返回 None（已处理行，归入 other）。
    """
    s = str(product_name).strip()
    m = re.match(r"颜色(?:分类)?:([^;]+)", s)
    return m.group(1).strip() if m else None


def _detect_brand(code: str) -> str:
    """
    根据编码格式判断品牌：
      - 含 '-'                      → camper   (如 K201636-002, 25WNTSK-002)
      - 前三位全字母（无 '-'）        → barbour  (如 MOL0726GN87)
      - 11 位纯数字                  → ecco     (如 06956301378)
      - 8  位纯数字                  → clarks   (如 26170510)
      - 其他                         → other
    """
    if "-" in code:
        return "camper"
    if re.match(r"[A-Za-z]{3}", code):
        return "barbour"
    if re.fullmatch(r"\d{11}", code):
        return "ecco"
    if re.fullmatch(r"\d{8}", code):
        return "clarks"
    return "other"


def split_excel_by_brand(input_path: str | Path, output_dir: str | Path) -> None:
    """
    将货品导出 Excel 按品牌拆分成多个文件。

    品牌判断逻辑（基于 "货品名称" 列）：
      - 以 "颜色分类:" 开头 → 解析编码，按格式区分 camper / ecco / clarks / other
      - 不以 "颜色分类:" 开头（已处理行）→ 直接归入 other，不重复解析

    Parameters
    ----------
    input_path : str | Path
        输入 Excel 文件路径。
    output_dir : str | Path
        输出目录；不存在时自动创建。
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(input_path, sheet_name=INPUT_SHEET_NAME, dtype=str).fillna("")

    if PRODUCT_NAME_COL not in df.columns:
        raise ValueError(
            f"列 '{PRODUCT_NAME_COL}' 不存在于输入文件中，"
            f"实际列名：{list(df.columns)}"
        )

    # 逐行打品牌标签
    def _label(val: str) -> str:
        code = _extract_code(val)
        return "other" if code is None else _detect_brand(code)

    df["__brand__"] = df[PRODUCT_NAME_COL].map(_label)

    # 按品牌分组写出，保持原始行顺序
    stem = input_path.stem
    totals: dict[str, int] = {}
    for brand, group in df.groupby("__brand__", sort=False):
        out_df = group.drop(columns=["__brand__"])
        out_file = output_dir / f"{stem}_{brand}.xlsx"
        out_df.to_excel(out_file, sheet_name=INPUT_SHEET_NAME or "Sheet1", index=False)
        totals[brand] = len(out_df)
        print(f"  {brand:10s}  {len(out_df):5d} 行  →  {out_file.name}")

    print(f"\n✅ 拆分完成，共 {sum(totals.values())} 行，{len(totals)} 个文件")
    print(f"📂 输出目录：{output_dir}")


# ======== 直接运行示例 ========
if __name__ == "__main__":
    input_file = Path(r"C:\Users\angel\Downloads\货品导出2026-05-11+22_54_26结果.xlsx")   # ← 修改为实际路径
    output_directory = Path(r"C:\Users\angel\Downloads")  # ← 修改为实际输出目录

    split_excel_by_brand(input_file, output_directory)
