import os
import datetime as dt
from pathlib import Path

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from channels.jingya.pricing.brand_discount_candidates import export_discount_itemids_to_ztc_txts


def generate_discouted_product():
    # 示例：本月

    export_discount_itemids_to_ztc_txts(
        brand="camper",
        min_discount_percent=34,
        taobao_store_excels_dir=r"D:\TB\Products\camper\document\store_prices",
        output_txt_dir=r"D:\TB\推广\discount",
        only_in_stock=True,
    )


    export_discount_itemids_to_ztc_txts(
        brand="geox",
        min_discount_percent=29,
        taobao_store_excels_dir=r"D:\TB\Products\geox\document\store_prices",
        output_txt_dir=r"D:\TB\推广\discount",
        only_in_stock=True,
    )


    export_discount_itemids_to_ztc_txts(
        brand="clarks_jingya",
        min_discount_percent=29,
        taobao_store_excels_dir=r"D:\TB\Products\clarks_jingya\document\store_prices",
        output_txt_dir=r"D:\TB\推广\discount",
        only_in_stock=True,
    )

    export_discount_itemids_to_ztc_txts(
        brand="ecco",
        min_discount_percent=29,
        taobao_store_excels_dir=r"D:\TB\Products\ecco\document\store_prices",
        output_txt_dir=r"D:\TB\推广\discount",
        only_in_stock=True,
    )



if __name__ == "__main__":
    generate_discouted_product()
