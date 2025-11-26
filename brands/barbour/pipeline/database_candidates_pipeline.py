from brands.barbour.common.barbour_import_candidates import import_from_txt, export_candidates_excel, import_codes_from_excel
from brands.barbour.common.fill_codes_into_txt import backfill_product_codes_to_txt


def pipeline_barbour():
    # 1) 先把 very 的 TXT 导入（有编码→products；无编码→candidates）
    import_from_txt("houseoffraser")

    # 2) 导出候选池为 Excel（首列 product_code 为空，等你手填）
    export_candidates_excel(r"D:\TB\Products\barbour\output\barbour_candidates.xlsx", True)

    # —— 人工在 Excel 里把 product_code 填好后 —— 
    # 3) 回填编码到 barbour_products（source_rank=2），并自动从候选池删除
    import_codes_from_excel(r"D:\TB\Products\barbour\output\barbour_candidates_20250914_082712.xlsx")

    # 4) 回填编码到 houseoffraser 的 TXT 文件，并重命名
    backfill_product_codes_to_txt("houseoffraser")


if __name__ == "__main__":
    pipeline_barbour()