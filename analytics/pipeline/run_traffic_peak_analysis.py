from analytics.ingest.analyze_new_item_traffic_peak import analyze_traffic_peak, TrafficPeakConfig
from analytics.pipeline.store_config import Store, get_active_stores


def run(store: Store, weeks: int = 4, metric: str = "visitors", brand: str | None = None):
    store.export_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{brand}" if brand else ""
    base = store.export_dir / f"traffic_peak_last{weeks}w{suffix}"
    analyze_traffic_peak(
        TrafficPeakConfig(
            weeks=weeks,
            metric=metric,
            brand=brand,
            store_name=store.store_name,
            output_path=str(base.with_suffix(".xlsx")),
            chart_path=str(base.with_suffix(".png")),
        )
    )


if __name__ == "__main__":
    for s in get_active_stores():
        print(f"\n========== 店铺：{s}，输出目录：{s.export_dir} ==========")
        run(s, weeks=4, metric="visitors", brand=None)
