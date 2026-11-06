from pathlib import Path
from cainiao.extract_goods_brand_from_order_excels import extract_goods_brand_info
from cainiao.generate_hscode_excel_barbour import generate_barbour_hscode
from cainiao.generate_hscode_excel_shoes import generate_shoe_hscode
from cainiao.hscode_audit import report_hscode_audit
from config import DOWNLOADS_DIR


 
def pipeline_jingya():

    output_dir = r"D:\TB\taofenxiao\海关备案"

    shoes_written, barbour_written, audit = extract_goods_brand_info(
        input_dir=str(DOWNLOADS_DIR),
        shoes_output=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
        barbour_output=r"D:\TB\taofenxiao\海关备案\barbour.xlsx"
    )

    generated_ids = set()
    issues = list(audit["issues"])

    if shoes_written:
        result = generate_shoe_hscode(
            input_list=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
            output_dir=output_dir,
            sheet_name="sheet1"
        )
        generated_ids |= result["generated_ids"]
        issues += result["issues"]
    else:
        print("[INFO] 本次没有鞋类品牌订单，跳过 generate_shoe_hscode。")

    #女装 6102300000
    #男装 6101909000

    if barbour_written:
        result = generate_barbour_hscode(
            input_list=r"D:\TB\taofenxiao\海关备案\barbour.xlsx",
            output_dir=output_dir,
            sheet_name="sheet1"
        )
        generated_ids |= result["generated_ids"]
        issues += result["issues"]
    else:
        print("[INFO] 本次没有 Barbour 订单，跳过 generate_barbour_hscode。")

    report_hscode_audit(output_dir, audit["order_ids"], generated_ids, issues, audit["ignored_files"])


if __name__ == "__main__":
    pipeline_jingya()