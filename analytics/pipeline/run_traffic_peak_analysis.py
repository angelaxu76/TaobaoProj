from analytics.ingest.analyze_new_item_traffic_peak import analyze_traffic_peak, TrafficPeakConfig
from analytics.pipeline.store_config import ACTIVE_STORE, EXPORT_DIR


def run(weeks: int = 4, metric: str = "visitors", brand: str | None = None):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{brand}" if brand else ""
    base = EXPORT_DIR / f"traffic_peak_last{weeks}w{suffix}"
    analyze_traffic_peak(
        TrafficPeakConfig(
            weeks=weeks,
            metric=metric,
            brand=brand,
            output_path=str(base.with_suffix(".xlsx")),
            chart_path=str(base.with_suffix(".png")),
        )
    )


if __name__ == "__main__":
    print(f"当前店铺：{ACTIVE_STORE}，输出目录：{EXPORT_DIR}")
    run(weeks=4, metric="visitors", brand=None)
