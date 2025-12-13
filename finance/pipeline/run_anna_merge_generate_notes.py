import os
import datetime as dt

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from finance.ingest.export_anna_supplier_orders_notes_v2 import generate_supplier_orders_excel,generate_anna_transactions_with_poe_excel


def run_supplier_orders_notes_pipeline():
    # 示例：本月
    start_date = dt.date(2025, 9, 1)
    end_date = dt.date(2025, 12, 31)

    filename = f"supplier_orders_notes_{start_date}_{end_date}.xlsx"
    output_path = os.path.join(r"C:\Users\martin\Desktop", filename)

    generate_anna_transactions_with_poe_excel(start_date, end_date, output_path)

    # generate_supplier_orders_excel_v3("2025-09-01", "2025-11-30", r"D:\supplier_orders_notes_v2.xlsx")



if __name__ == "__main__":
    run_supplier_orders_notes_pipeline()
