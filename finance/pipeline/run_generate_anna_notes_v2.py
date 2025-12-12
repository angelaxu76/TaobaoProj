import os
import datetime as dt

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from finance.ingest.export_anna_supplier_orders_notes import generate_supplier_orders_excel


def run_supplier_orders_notes_pipeline():
    # 示例：本月
    start_date = dt.date(2025, 10, 1)
    end_date = dt.date(2025, 12, 31)

    filename = f"supplier_orders_notes_{start_date}_{end_date}.xlsx"
    output_path = os.path.join("d:/", filename)

    generate_supplier_orders_excel(start_date, end_date, output_path)


if __name__ == "__main__":
    run_supplier_orders_notes_pipeline()
