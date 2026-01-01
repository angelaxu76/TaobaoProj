from product_analytics.ingest.export_brand_bad_products_report import (
    export_brand_bad_products_report, ExportConfig
)

def product_export():
    export_brand_bad_products_report(
        ExportConfig(
            brand="camper",
            days=30,
            output_path=r"D:\TB\product_analytics\export\CAMPER_bad_products_last30d.xlsx",
            split_by_store=False,
            min_publication_date=None,  # 不写也行
        )
    )

if __name__ == "__main__":
    product_export()