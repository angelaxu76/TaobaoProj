from analytics.ingest.export_brand_bad_products_report_v2 import (
    export_brand_bad_products_report, ExportConfig
)

def product_export():
    export_brand_bad_products_report(
        ExportConfig(
            brand="barbour",
            days=20,
            output_path=r"D:\TB\product_analytics\export\barbour_products_last20d_2026.xlsx",
            split_by_store=False,
            min_publication_date=None,  # 不写也行
        )
    )

if __name__ == "__main__":
    product_export()