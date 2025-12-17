import os
import datetime as dt
from pathlib import Path
from config import PGSQL_CONFIG

from channels.jingya.check.channel_price_check import (
    check_taobao_margin_safety
)

from channels.jingya.check.jingya_taobao_price_diff_validate import check_taobao_item_price_diff

def taobao_price_validate():
    # 示例：本月
    # CLARKS 价格检查是否倒挂

    # clarks 英国伦敦代购
    check_taobao_item_price_diff(
    brand="clarks_jingya",
    taobao_excel_path=r"D:\TB\maintain\store_prices_export\英国伦敦代购clarks.xlsx",
    output_report_path=r"D:\TB\maintain\store_prices_report\英国伦敦代购clarks_report.xlsx",
    )



if __name__ == "__main__":
    taobao_price_validate()
