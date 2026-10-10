import psycopg2
from pathlib import Path

from cfg.db_config import PGSQL_CONFIG
from analytics.ingest.import_catalog_items_from_excel import import_catalog_items_from_excel, ensure_store_name_column
from analytics.ingest.import_product_metrics_daily_from_excel import import_product_metrics_daily
from analytics.pipeline.store_config import Store, get_active_stores, BRAND_KEYWORDS, RESET_ALL_BEFORE_IMPORT


def reset_all_tables() -> None:
    """清空两张分析表的全部数据（所有店铺），保留表结构。"""
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE product_metrics_daily, catalog_items RESTART IDENTITY CASCADE;")
        conn.commit()
        print("✅ 已清空 catalog_items 与 product_metrics_daily 的全部数据（所有店铺）")
    finally:
        conn.close()


def reset_store_catalog(store: Store) -> None:
    """
    多店铺：只清空当前店铺的商品信息（catalog_items），其它店铺数据保留。
    - 商品信息每次全量重导，删掉旧的才能去掉已下架的链接
    - 日报（product_metrics_daily）不删，按 (stat_date, item_id, store_name) upsert
    - store_name IS NULL 是升级前单店铺模式留下的旧数据，一并清掉
    """
    conn = psycopg2.connect(**PGSQL_CONFIG)
    try:
        ensure_store_name_column(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM catalog_items WHERE store_name = %s OR store_name IS NULL;",
                (store.store_name,),
            )
            n = cur.rowcount
        conn.commit()
        print(f"✅ 已清空当前店铺商品信息 {n} 条（{store}），其它店铺数据保留")
    finally:
        conn.close()


def product_import(store: Store):
    print(f"\n========== 导入店铺：{store} ==========")
    reset_store_catalog(store)

    catalog_dir = store.catalog_dir
    metrics_dir = store.metrics_dir
    catalog_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # ── catalog（商品信息）──────────────────────────────────────
    excels = sorted(catalog_dir.glob("*.xlsx"))
    if not excels:
        print(f"⚠️ 目录下没有找到 xlsx 文件：{catalog_dir}")
    else:
        total_ins = total_upd = total_skip = 0
        for path in excels:
            result = import_catalog_items_from_excel(
                excel_path=str(path),
                sheet_name=None,
                create_unique_index=True,
                brand_keywords=BRAND_KEYWORDS,
                store_name=store.store_name,
            )
            total_ins  += result["inserted"]
            total_upd  += result["updated"]
            total_skip += result["skipped"]
            print(f"  {path.name} → 新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}")
        print(f"✅ catalog 汇总（共 {len(excels)} 个文件）：新增 {total_ins}，更新 {total_upd}，跳过 {total_skip}")

    # ── 日报（每月一个 xlsx，直接扫描目录）──────────────────────
    metrics_files = sorted(metrics_dir.glob("*.xlsx"))
    if not metrics_files:
        print(f"⚠️ 目录下没有找到 xlsx 文件：{metrics_dir}")
    else:
        for path in metrics_files:
            n = import_product_metrics_daily(str(path), expected_store_name=store.store_name)
            print(f"  {path.name} → 导入 {n} 行")


if __name__ == "__main__":
    stores = get_active_stores()
    print(f"本次导入店铺：{'、'.join(str(s) for s in stores)}")
    if RESET_ALL_BEFORE_IMPORT:
        reset_all_tables()
    else:
        print("增量导入模式：保留其它店铺数据和历史日报")
    for s in stores:
        product_import(s)
