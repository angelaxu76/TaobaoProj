# -*- coding: utf-8 -*-
"""
tool_merge_colors.py
────────────────────
将 generate_publication_excel 生成的发布 Excel 按款式合并多色。

规则：
  - 商品编码前 7 位相同 → 视为同一款式（如 MML0012PI95 / MML0012NY91 → 款式 MML0012）
  - 合并后保留第一行的所有字段
  - 新增"多颜色编码"列：该款式所有颜色编码逗号分隔（含第一行自身）
  - 输出文件名在原文件名后追加 _merged

用法：
  1. 直接运行：python -m brands.barbour.pipeline.tool_merge_colors
     （会自动找 PUBLICATION_DIR 下最新的 barbour_publication_*.xlsx）
  2. 代码调用：merge_colors_excel(Path("path/to/file.xlsx"))
"""

from pathlib import Path
import pandas as pd
from config import BARBOUR


PUBLICATION_DIR: Path = BARBOUR["PUBLICATION_DIR"]
CODE_COL = "商品编码"          # 与 generate_publication_excel 输出头部保持一致
STYLE_LEN = 7                  # 前 7 位为款式编码


def merge_colors_excel(input_path: Path) -> Path:
    """
    读取 input_path，按前 7 位编码合并多色，输出 *_merged.xlsx。
    返回输出文件路径。
    """
    df = pd.read_excel(input_path, dtype=str)

    if CODE_COL not in df.columns:
        raise SystemExit(
            f"❌ 找不到列 '{CODE_COL}'，请确认 Excel 是 generate_publication_excel 生成的。"
            f"\n实际列名：{list(df.columns)}"
        )

    # 款式 key（前 7 位）
    df["_style_key"] = df[CODE_COL].str.strip().str[:STYLE_LEN]

    # 按 _style_key 聚合所有编码
    all_codes_by_style = (
        df.groupby("_style_key", sort=False)[CODE_COL]
        .apply(lambda s: ", ".join(s.tolist()))
        .rename("多颜色编码")
    )

    # 每款只保留第一行
    deduped = df.drop_duplicates(subset="_style_key", keep="first").copy()

    # 合并"多颜色编码"列
    deduped = deduped.join(all_codes_by_style, on="_style_key")

    # 把"多颜色编码"插到"商品编码"右侧
    code_idx = deduped.columns.get_loc(CODE_COL)
    cols = list(deduped.columns)
    cols.remove("多颜色编码")
    cols.remove("_style_key")
    cols.insert(code_idx + 1, "多颜色编码")
    deduped = deduped[cols]

    # 统计
    total_in  = len(df)
    total_out = len(deduped)
    multi = (deduped["多颜色编码"].str.contains(",")).sum()
    print(f"📊 合并前：{total_in} 行  合并后：{total_out} 行  多色款：{multi} 款")

    # 输出
    output_path = input_path.with_name(input_path.stem + "_merged.xlsx")
    deduped.to_excel(output_path, index=False)
    print(f"✅ 已输出：{output_path}")
    return output_path


def _latest_publication_excel(pub_dir: Path) -> Path:
    """找 PUBLICATION_DIR 下最新的 barbour_publication_*.xlsx（不含 _merged）。"""
    candidates = sorted(
        [f for f in pub_dir.glob("barbour_publication_*.xlsx") if "_merged" not in f.name],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"❌ 在 {pub_dir} 找不到 barbour_publication_*.xlsx")
    return candidates[0]


if __name__ == "__main__":
    target = _latest_publication_excel(PUBLICATION_DIR)
    print(f"🔍 处理文件：{target}")
    merge_colors_excel(target)
