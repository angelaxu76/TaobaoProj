import psycopg2

from cfg.db_config import PGSQL_CONFIG
from analytics.ingest.export_cross_store_comparison import export_cross_store_comparison, CrossStoreConfig
from analytics.pipeline.store_config import CROSS_STORE_EXPORT_DIR, STORE_NAME_MAP


def print_loaded_stores() -> None:
    """导出前打印库里各店铺的数据量，确认三个店铺都已导入。"""
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT store_name, COUNT(*) FROM catalog_items GROUP BY store_name ORDER BY store_name;")
            catalog = dict(cur.fetchall())
            cur.execute("SELECT store_name, COUNT(*), MAX(stat_date) FROM product_metrics_daily GROUP BY store_name ORDER BY store_name;")
            daily = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    finally:
        conn.close()

    print("库中店铺数据：")
    for folder, store in STORE_NAME_MAP.items():
        n_daily, last_date = daily.get(store, (0, None))
        print(f"  {folder:<8} {store:<10} 商品 {catalog.get(store, 0):>6} 条，日报 {n_daily:>7} 行，最新日期 {last_date}")
    unknown = (set(catalog) | set(daily)) - set(STORE_NAME_MAP.values())
    if unknown:
        print(f"  ⚠️ 未在 STORE_NAME_MAP 中的店铺：{sorted(map(str, unknown))}")


def cross_store_export(brand: str | None, days: int = 30, min_store_cnt: int = 2):
    CROSS_STORE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    label = brand or "all"
    export_cross_store_comparison(
        CrossStoreConfig(
            brand=brand,
            days=days,
            min_store_cnt=min_store_cnt,
            output_path=str(CROSS_STORE_EXPORT_DIR / f"{label}_cross_store_last{days}d.xlsx"),
        )
    )


if __name__ == "__main__":
    print_loaded_stores()
    print(f"输出目录：{CROSS_STORE_EXPORT_DIR}")
    for b in ["barbour", "camper", "ecco", "clarks", "geox"]:
        cross_store_export(b)
