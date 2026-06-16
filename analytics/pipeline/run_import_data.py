import psycopg2
from pathlib import Path

from cfg.db_config import PGSQL_CONFIG
from analytics.ingest.import_catalog_items_from_excel import import_catalog_items_from_excel
from analytics.ingest.import_product_metrics_daily_from_excel import import_product_metrics_daily
from analytics.pipeline.store_config import ACTIVE_STORE, CATALOG_DIR, METRICS_DIR, BRAND_KEYWORDS


def reset_analytics_tables() -> None:
    """切换店铺时清空旧数据，保留表结构。"""
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE product_metrics_daily, catalog_items RESTART IDENTITY CASCADE;")
        conn.commit()
        print(f"✅ 已清空 catalog_items 与 product_metrics_daily（当前店铺：{ACTIVE_STORE}）")
    finally:
        conn.close()


def product_import():
    reset_analytics_tables()

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    # ── catalog（商品信息）──────────────────────────────────────
    excels = sorted(CATALOG_DIR.glob("*.xlsx"))
    if not excels:
        print(f"⚠️ 目录下没有找到 xlsx 文件：{CATALOG_DIR}")
    else:
        total_ins = total_upd = total_skip = 0
        for path in excels:
            result = import_catalog_items_from_excel(
                excel_path=str(path),
                sheet_name=None,
                create_unique_index=True,
                brand_keywords=BRAND_KEYWORDS,
            )
            total_ins  += result["inserted"]
            total_upd  += result["updated"]
            total_skip += result["skipped"]
            print(f"  {path.name} → 新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}")
        print(f"✅ catalog 汇总（共 {len(excels)} 个文件）：新增 {total_ins}，更新 {total_upd}，跳过 {total_skip}")

    # ── 日报（每月一个 xlsx，直接扫描目录）──────────────────────
    metrics_files = sorted(METRICS_DIR.glob("*.xlsx"))
    if not metrics_files:
        print(f"⚠️ 目录下没有找到 xlsx 文件：{METRICS_DIR}")
    else:
        for path in metrics_files:
            n = import_product_metrics_daily(str(path))
            print(f"  {path.name} → 导入 {n} 行")


if __name__ == "__main__":
    product_import()
