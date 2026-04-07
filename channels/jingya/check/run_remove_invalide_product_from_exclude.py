import os
import datetime as dt
from pathlib import Path
from config import PGSQL_CONFIG

from channels.jingya.check.exclude_by_product_code_txt import exclude_excel_rows_by_txt


def taobao_price_validate():

    # print("\\n🟡 Step:clarks jingya")
    # exclude_excel_rows_by_txt(
    # excel_path=r"D:\TB\Products\clarks\document\exclude.xlsx",
    # txt_path=r"D:\TB\Products\clarks\document\exclude_codes.txt",
    # output_path=r"D:\TB\Products\clarks\document\exclude.xlsx",  # 覆盖
    # )

    # print("\\n🟡 Step: camper")
    # exclude_excel_rows_by_txt(
    # excel_path=r"D:\TB\Products\camper\document\camper_blacklist_excel.xlsx",
    # txt_path=r"D:\TB\Products\camper\document\exclude_codes.txt",
    # output_path=r"D:\TB\Products\camper\document\camper_blacklist_excel.xlsx",  # 覆盖
    # )

    print("\\n🟡 ecco ")
    exclude_excel_rows_by_txt(
    excel_path=r"D:\TB\Products\ecco\document\exclude.xlsx",
    txt_path=r"D:\TB\Products\ecco\document\exclude_codes.txt",
    output_path=r"D:\TB\Products\ecco\document\exclude.xlsx",  # 覆盖
    )

    # print("\\n🟡 geox")
    # exclude_excel_rows_by_txt(
    # excel_path=r"D:\TB\Products\clarks\document\exclude.xlsx",
    # txt_path=r"D:\TB\Products\clarks\document\exclude_codes.txt",
    # output_path=r"D:\TB\Products\clarks\document\exclude.xlsx",  # 覆盖
    # )




if __name__ == "__main__":
    taobao_price_validate()