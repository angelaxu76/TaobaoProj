from pathlib import Path
from channels.jingya.cainiao.extract_goods_brand_from_order_excels import extract_goods_brand_info
from channels.jingya.cainiao.generate_hscode_excel_barbour import generate_barbour_hscode
from channels.jingya.cainiao.generate_hscode_excel_shoes import generate_shoe_hscode
from config import DOWNLOADS_DIR


 
def pipeline_jingya():

    shoes_written, barbour_written = extract_goods_brand_info(
        input_dir=str(DOWNLOADS_DIR),
        shoes_output=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
        barbour_output=r"D:\TB\taofenxiao\海关备案\barbour.xlsx"
    )

    if shoes_written:
        generate_shoe_hscode(
            input_list=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
            output_dir=r"D:\TB\taofenxiao\海关备案",
            sheet_name="sheet1"
        )
    else:
        print("[INFO] 本次没有鞋类品牌订单，跳过 generate_shoe_hscode。")

    #女装 6102300000
    #男装 6101909000

    if barbour_written:
        generate_barbour_hscode(
            input_list=r"D:\TB\taofenxiao\海关备案\barbour.xlsx",
            output_dir=r"D:\TB\taofenxiao\海关备案",
            sheet_name="sheet1"
        )
    else:
        print("[INFO] 本次没有 Barbour 订单，跳过 generate_barbour_hscode。")


if __name__ == "__main__":
    pipeline_jingya()