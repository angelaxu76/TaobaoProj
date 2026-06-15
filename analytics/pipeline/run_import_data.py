import os
import datetime as dt
from pathlib import Path

# from config import TOOL_OUTPUT_DIR  # 比如你自定义的输出目录
from analytics.ingest.import_catalog_items_from_excel import import_catalog_items_from_excel
from analytics.ingest.import_product_metrics_daily_from_excel import import_product_metrics_daily


def product_import():
    CATALOG_DIR = r"D:\TB\product_analytics\input_data\product_info"

    excels = sorted(Path(CATALOG_DIR).glob("*.xlsx"))
    if not excels:
        print(f"⚠️ 目录下没有找到 xlsx 文件：{CATALOG_DIR}")
        return

    total_ins = total_upd = total_skip = 0
    for path in excels:
        result = import_catalog_items_from_excel(
            excel_path=str(path),
            sheet_name=None,
            create_unique_index=True,
        )
        total_ins  += result["inserted"]
        total_upd  += result["updated"]
        total_skip += result["skipped"]
        print(f"  {path.name} → 新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}")

    print(f"✅ catalog 汇总（共 {len(excels)} 个文件）：新增 {total_ins}，更新 {total_upd}，跳过 {total_skip}")


    # EXCEL_PATH = r"D:\TB\analytics\input_data\daily_metrics\252507.xlsx"
    # n = import_product_metrics_daily(EXCEL_PATH)
    # print(f"✅ 导入完成：{n} 行")

    import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\202606.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\252508.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\252509.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\252510.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\252511.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\202512.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\202601.xlsx")
    # import_product_metrics_daily(r"D:\TB\product_analytics\input_data\daily_metrics\202602.xlsx")


if __name__ == "__main__":
    product_import()
