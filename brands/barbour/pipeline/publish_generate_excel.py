from pathlib import Path
import pandas as pd
from config import BARBOUR
from brands.barbour.common.generate_publication_excel import generate_publication_excel
from brands.barbour.common.export_discounts import export_barbour_discounts_excel, export_barbour_discounts_excel_multi

# codes.xlsx 路径与 ops/linkfox/_session_config.py 保持一致
CODES_XLSX = BARBOUR["OUTPUT_DIR"] / "codes.xlsx"


def _save_codes_to_xlsx(excel_path: Path, codes_xlsx: Path = CODES_XLSX) -> int:
    """从折扣候选 Excel 的 product_code 列提取编码，写入 codes.xlsx。"""
    df = pd.read_excel(excel_path, sheet_name=0, usecols=["product_code"])
    codes = (
        df["product_code"]
        .dropna()
        .astype(str)
        .str.strip()
        .pipe(lambda s: s[s != ""])
        .tolist()
    )
    codes_xlsx.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"product_code": codes}).to_excel(codes_xlsx, index=False)
    print(f"✅ 已写入 {len(codes)} 个编码 → {codes_xlsx}")
    return len(codes)


def pipeline_barbour():
    print("\n🚀 启动 Barbour 发布流程")

    # ── 步骤 1：导出折扣候选商品到 Excel ────────────────────────────
    # 取消注释需要的那一行（women / men）：
    # excel_path = export_barbour_discounts_excel_multi(0, 3, "LWX,LSP,LWB,LCA,LOL,LGI")
    # excel_path = export_barbour_discounts_excel_multi(0, 3, "MWX,MQU,MOL,MWB,MFL,MOS,MCA,MFL")
    # excel_path = export_barbour_discounts_excel_multi(0, 3, "MTS,MSH,MML,MOS")
    # excel_path = export_barbour_discounts_excel_multi(0, 3, "MML")
    # print(excel_path)

    # ── 步骤 2：将 Excel 中的商品编码自动写入 codes.xlsx ────────────
    # （取消步骤 1 注释后，同时取消下面这行）
    # _save_codes_to_xlsx(excel_path)

    # ── 步骤 3：根据 codes.txt 生成发布 Excel ────────────────────────
    generate_publication_excel()


if __name__ == "__main__":
    pipeline_barbour()