from pathlib import Path
from channels.jingya.cainiao.extract_goods_brand_from_order_excels import extract_goods_brand_info
from channels.jingya.cainiao.generate_hscode_excel_barbour import generate_barbour_hscode
from channels.jingya.cainiao.generate_hscode_excel_shoes import generate_shoe_hscode


 
def pipeline_jingya():

    # extract_goods_brand_info(
    #     input_dir=r"C:\Users\martin\Downloads",
    #     shoes_output=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
    #     barbour_output=r"D:\TB\taofenxiao\海关备案\barbour.xlsx"
    # )

    # generate_shoe_hscode(
    #     input_list=r"D:\TB\taofenxiao\海关备案\shoes.xlsx",
    #     output_dir=r"D:\TB\taofenxiao\海关备案",
    #     sheet_name="sheet1"
    # )



    #女装 6102300000 
    #男装 6101909000

    generate_barbour_hscode(
        input_list=r"D:\TB\taofenxiao\海关备案\barbour.xlsx",
        output_dir=r"D:\TB\taofenxiao\海关备案",
        sheet_name="sheet1"
    )


if __name__ == "__main__":
    pipeline_jingya()