from analytics.ingest.export_brand_bad_products_report_v2 import (
    export_brand_bad_products_report, ExportConfig
)
from analytics.pipeline.store_config import ACTIVE_STORE, EXPORT_DIR


def product_export(brand: str, days: int = 30):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = str(EXPORT_DIR / f"{brand}_products_last{days}d.xlsx")
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
    print(f"当前店铺：{ACTIVE_STORE}，输出目录：{EXPORT_DIR}")
    product_export("barbour")
    product_export("camper")
    product_export("ecco")
    product_export("clarks")
    product_export("geox")
