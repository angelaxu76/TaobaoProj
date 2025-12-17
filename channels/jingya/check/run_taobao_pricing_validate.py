import os
import datetime as dt
from pathlib import Path
from config import PGSQL_CONFIG

from channels.jingya.check.jingya_taobao_price_diff_validate import check_taobao_item_price_diff
from channels.jingya.check.exclude_by_product_code_txt import exclude_excel_rows_by_txt


def taobao_price_validate():
    # 示例：本月
    # CLARKS 价格检查是否倒挂

    # clarks 英国伦敦代购
    check_taobao_item_price_diff(
    brand="clarks_jingya",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\英国伦敦代购clarks.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\英国伦敦代购clarks_report.xlsx",
    )

    # camper 英国伦敦代购
    check_taobao_item_price_diff(
    brand="camper",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\英国伦敦代购camper.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\英国伦敦代购camper_report.xlsx",
    )

    # ecco 英国伦敦代购
    check_taobao_item_price_diff(
    brand="ecco",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\英国伦敦代购ecco.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\英国伦敦代购ecco_report.xlsx",
    )

    # geox 英国伦敦代购
    check_taobao_item_price_diff(
    brand="geox",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\英国伦敦代购geox.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\英国伦敦代购geox_report.xlsx",
    )





    # clarks 五小剑
    check_taobao_item_price_diff(
    brand="clarks_jingya",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\五小剑clarks.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\五小剑clarks_report.xlsx",
    )

    # camper 五小剑
    check_taobao_item_price_diff(
    brand="camper",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\五小剑camper.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\五小剑camper_report.xlsx",
    )

    # ecco 五小剑
    check_taobao_item_price_diff(
    brand="ecco",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\五小剑ecco.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\五小剑ecco_report.xlsx",
    )

    # geox 五小剑
    check_taobao_item_price_diff(
    brand="geox",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\五小剑geox.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\五小剑geox_report.xlsx",
    )




    # exclude_excel_rows_by_txt(
    # excel_path=r"D:\TB\Products\clarks_jingya\document\exclude.xlsx",
    # txt_path=r"D:\TB\Products\clarks_jingya\document\exclude_codes.txt",
    # output_path=r"D:\TB\Products\clarks_jingya\document\exclude.xlsx",  # 覆盖
    # )





if __name__ == "__main__":
    taobao_price_validate()
