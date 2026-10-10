from analytics.ingest.export_brand_bad_products_report_v2 import (
    export_brand_bad_products_report, ExportConfig
)
from analytics.pipeline.store_config import (
    Store, get_active_stores,
    FILTER_PAY_AMOUNT_MAX, FILTER_VISITORS_MAX, FILTER_PUBLICATION_WEEKS,
)


def product_export(store: Store, brand: str, days: int = 30):
    store.export_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(store.export_dir / f"{brand}_products_last{days}d.xlsx")
    export_brand_bad_products_report(
        ExportConfig(
            brand=brand,
            days=days,
            output_path=output_path,
            store_name=store.store_name,
            split_by_store=False,
            min_publication_date=None,
            filter_pay_amount_max=FILTER_PAY_AMOUNT_MAX,
            filter_visitors_max=FILTER_VISITORS_MAX,
            filter_publication_weeks=FILTER_PUBLICATION_WEEKS,
        )
    )


if __name__ == "__main__":
    for s in get_active_stores():
        print(f"\n========== 导出店铺：{s}，输出目录：{s.export_dir} ==========")
        product_export(s, "barbour")
        product_export(s, "camper")
        product_export(s, "ecco")
        product_export(s, "clarks")
        product_export(s, "geox")
