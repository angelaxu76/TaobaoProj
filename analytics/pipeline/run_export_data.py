from analytics.ingest.export_brand_bad_products_report_v2 import (
    export_brand_bad_products_report, ExportConfig
)

def product_export(brand: str, output_path: str, days: int = 30):
    export_brand_bad_products_report(
        ExportConfig(
            brand=brand,
            days=days,
            output_path=output_path,
            split_by_store=False,
            min_publication_date=None,
        )
    )

if __name__ == "__main__":
    product_export("barbour",  r"D:\TB\product_analytics\export\barbour_products_last20d_2026.xlsx")
    product_export("camper",   r"D:\TB\product_analytics\export\camper_products_last20d_2026.xlsx")
    product_export("ecco",     r"D:\TB\product_analytics\export\ecco_products_last20d_2026.xlsx")
    product_export("clarks",   r"D:\TB\product_analytics\export\clarks_products_last20d_2026.xlsx")
    product_export("geox",     r"D:\TB\product_analytics\export\geox_products_last20d_2026.xlsx")
