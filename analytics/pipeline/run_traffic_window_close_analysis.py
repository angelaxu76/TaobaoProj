from analytics.ingest.analyze_traffic_window_close import analyze_traffic_window_close, WindowCloseConfig
from analytics.pipeline.store_config import ACTIVE_STORE, EXPORT_DIR


def run(weeks: int = 4, metric: str = "visitors", brand: str | None = None,
        max_day: int = 20, trailing_check_days: int = 7):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{brand}" if brand else ""
    base = EXPORT_DIR / f"traffic_window_close{suffix}"
    analyze_traffic_window_close(
        WindowCloseConfig(
            weeks=weeks,
            metric=metric,
            brand=brand,
            max_day=max_day,
            trailing_check_days=trailing_check_days,
            output_path=str(base.with_suffix(".xlsx")),
            chart_path=str(base.with_suffix(".png")),
        )
    )


if __name__ == "__main__":
    print(f"当前店铺：{ACTIVE_STORE}，输出目录：{EXPORT_DIR}")
    run(weeks=4, metric="visitors", brand=None, max_day=20, trailing_check_days=7)
