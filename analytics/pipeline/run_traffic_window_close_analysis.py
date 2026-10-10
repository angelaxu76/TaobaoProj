from analytics.ingest.analyze_traffic_window_close import analyze_traffic_window_close, WindowCloseConfig
from analytics.pipeline.store_config import Store, get_active_stores


def run(store: Store, weeks: int = 4, metric: str = "visitors", brand: str | None = None,
        max_day: int = 20, trailing_check_days: int = 7):
    store.export_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{brand}" if brand else ""
    base = store.export_dir / f"traffic_window_close{suffix}"
    analyze_traffic_window_close(
        WindowCloseConfig(
            weeks=weeks,
            metric=metric,
            brand=brand,
            store_name=store.store_name,
            max_day=max_day,
            trailing_check_days=trailing_check_days,
            output_path=str(base.with_suffix(".xlsx")),
            chart_path=str(base.with_suffix(".png")),
        )
    )


if __name__ == "__main__":
    for s in get_active_stores():
        print(f"\n========== 店铺：{s}，输出目录：{s.export_dir} ==========")
        run(s, weeks=4, metric="visitors", brand=None, max_day=20, trailing_check_days=7)
