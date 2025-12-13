import os
import datetime as dt
from pathlib import Path

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from finance.ingest.import_anna_transactions import import_anna_file


def anna_import():
    # 示例：本月

    input_excel = Path(r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\账目统计\anna_20251001-20251131.xlsx")

    import_anna_file(input_excel)



if __name__ == "__main__":
    anna_import()
