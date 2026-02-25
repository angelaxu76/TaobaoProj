import os
import datetime as dt
from pathlib import Path

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from analytics.ingest.import_catalog_items_from_excel import import_catalog_items_from_excel
from analytics.ingest.import_product_metrics_daily_from_excel import import_product_metrics_daily


def product_import():
    # 示例：本月

    EXCEL_PATH = r"D:\TB\analytics\input_data\product_info\商品统计_20251230.xlsx"

    ins, upd, skip = import_catalog_items_from_excel(
        excel_path=EXCEL_PATH,
        sheet_name=None,
        create_unique_index=True,
    )

    

    print(f"✅ 导入完成：新增 {ins}，更新 {upd}，跳过 {skip}")


    # EXCEL_PATH = r"D:\TB\analytics\input_data\daily_metrics\252507.xlsx"
    # n = import_product_metrics_daily(EXCEL_PATH)
    # print(f"✅ 导入完成：{n} 行")

    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\252507.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\252508.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\252509.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\252510.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\252511.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\202512.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\202601.xlsx")
    import_product_metrics_daily(r"D:\TB\analytics\input_data\daily_metrics\202602.xlsx")


if __name__ == "__main__":
    product_import()
