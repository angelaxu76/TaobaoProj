# check_jingya_stock_mismatch.py
"""
库存核对：数据库库存 vs 鲸芽导出的最新库存表（GEI@sales_catalogue_export@...xlsx）。

匹配粒度：skuid

用法示例：
    # 不传 --excel 时，自动去 GEI_EXPORT_BASE/<品牌>/ 下找最新的 GEI*.xlsx
    python -m channels.jingya.check.check_jingya_stock_mismatch --brand clarks

    # 手动指定 Excel 路径
    python -m channels.jingya.check.check_jingya_stock_mismatch \
        --brand clarks \
        --excel "E:\\shared\\GEI_SHARED\\clarks\\GEI@sales_catalogue_export@260628021100@0674.xlsx"
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2

from config import BRAND_CONFIG, PGSQL_CONFIG, GEI_EXPORT_BASE


def _find_latest_gei_excel(brand: str) -> str:
    """
    在 GEI_EXPORT_BASE/<品牌>/ 下查找最新的鲸芽导出Excel（文件名以 GEI 开头）。
    忽略打开文件时产生的临时文件（~$ 开头）。
    """
    brand_l = brand.lower().strip()
    search_dir = Path(GEI_EXPORT_BASE) / brand_l
    if not search_dir.exists():
        raise FileNotFoundError(f"未找到品牌目录: {search_dir}")

    candidates = [
        p for p in search_dir.glob("GEI*.xlsx")
        if not p.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError(f"{search_dir} 下未找到 GEI*.xlsx 文件")

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    print(f"[INFO] 自动匹配到最新鲸芽导出文件: {latest}")
    return str(latest)


def _get_pg_conn_and_table(brand: str):
    brand_l = brand.lower().strip()
    if brand_l not in BRAND_CONFIG:
        raise ValueError(f"未知品牌: {brand}。可用: {', '.join(sorted(BRAND_CONFIG.keys()))}")

    cfg = BRAND_CONFIG[brand_l]
    table_name = cfg["TABLE_NAME"]
    pgcfg = cfg.get("PGSQL_CONFIG", PGSQL_CONFIG)

    conn = psycopg2.connect(
        host=pgcfg["host"],
        port=pgcfg["port"],
        user=pgcfg["user"],
        password=pgcfg["password"],
        dbname=pgcfg["dbname"],
    )
    return conn, table_name


def _fetch_db_stock(brand: str) -> pd.DataFrame:
    """
    读取数据库中已绑定渠道的库存（skuid + channel_product_id 均非空）。
    """
    conn, table_name = _get_pg_conn_and_table(brand)

    sql = f"""
        SELECT
            skuid,
            channel_product_id,
            product_code,
            product_title,
            stock_count
        FROM {table_name}
        WHERE skuid IS NOT NULL AND TRIM(skuid) <> ''
          AND channel_product_id IS NOT NULL AND TRIM(channel_product_id) <> ''
    """
    df_db = pd.read_sql(sql, conn)
    conn.close()

    df_db["skuid"] = df_db["skuid"].astype(str).str.strip()
    df_db["product_code"] = df_db["product_code"].fillna("").astype(str).str.strip()
    df_db["product_title"] = df_db["product_title"].fillna("").astype(str).str.strip()
    df_db["stock_count"] = pd.to_numeric(df_db["stock_count"], errors="coerce").fillna(0).astype(int)

    return df_db


def _find_col(want: str, cols) -> Optional[str]:
    if want in cols:
        return want
    want_norm = want.replace(" ", "").lower()
    for c in cols:
        if str(c).replace(" ", "").lower() == want_norm:
            return c
    return None


def _read_jingya_stock_excel(
    jingya_excel_path: str,
    excel_skuid_col: str = "skuID",
    excel_stock_col: str = "可售库存",
    excel_title_col: str = "渠道产品名称",
    excel_status_col: str = "铺货状态",
) -> pd.DataFrame:
    """
    读取鲸芽导出的渠道产品目录（GEI@sales_catalogue_export@...xlsx）。
    """
    df_xy = pd.read_excel(jingya_excel_path)
    df_xy = df_xy.rename(columns={c: str(c).strip() for c in df_xy.columns})

    mapping_spec = {
        excel_skuid_col: "skuid",
        excel_stock_col: "jy_stock",
        excel_title_col: "excel_channel_title",
        excel_status_col: "listing_status",
    }

    final_map = {}
    for want_src, std_name in mapping_spec.items():
        real_col = _find_col(want_src, df_xy.columns)
        if real_col is None:
            raise KeyError(f"鲸芽Excel中缺少列: {want_src}（现有列: {list(df_xy.columns)}）")
        final_map[real_col] = std_name

    df_xy = df_xy.rename(columns=final_map)[list(final_map.values())]

    df_xy["skuid"] = df_xy["skuid"].astype(str).str.strip()
    df_xy["excel_channel_title"] = df_xy["excel_channel_title"].fillna("").astype(str).str.strip()
    df_xy["listing_status"] = df_xy["listing_status"].fillna("").astype(str).str.strip()
    df_xy["jy_stock"] = pd.to_numeric(df_xy["jy_stock"], errors="coerce")

    # 同一 skuid 若有重复行，保留库存非空的一行
    df_xy = df_xy.sort_values("jy_stock", na_position="last").drop_duplicates("skuid", keep="first")

    return df_xy


def _export_stock_diff_report(
    df_mismatch: pd.DataFrame,
    df_missing_in_excel: pd.DataFrame,
    df_missing_in_db: pd.DataFrame,
    output_report_path: str,
) -> str:
    out_path = Path(output_report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mismatch_cols = [
        "channel_product_id", "skuid", "product_code", "final_title",
        "stock_count", "jy_stock", "diff", "listing_status",
    ]
    missing_excel_cols = [
        "channel_product_id", "skuid", "product_code", "product_title", "stock_count",
    ]
    missing_db_cols = [
        "skuid", "excel_channel_title", "jy_stock", "listing_status",
    ]

    for df, cols in (
        (df_mismatch, mismatch_cols),
        (df_missing_in_excel, missing_excel_cols),
        (df_missing_in_db, missing_db_cols),
    ):
        for c in cols:
            if c not in df.columns:
                df[c] = None

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_mismatch[mismatch_cols].to_excel(writer, index=False, sheet_name="stock_mismatch")
        df_missing_in_excel[missing_excel_cols].to_excel(writer, index=False, sheet_name="missing_in_jingya_export")
        df_missing_in_db[missing_db_cols].to_excel(writer, index=False, sheet_name="missing_in_db")

    print(f"[OK] 库存差异报告导出: {out_path}")
    return str(out_path)


def check_jingya_stock_mismatch(
    brand: str,
    jingya_excel_path: Optional[str] = None,
    output_report_path: Optional[str] = None,
    excel_skuid_col: str = "skuID",
    excel_stock_col: str = "可售库存",
    excel_title_col: str = "渠道产品名称",
    excel_status_col: str = "铺货状态",
    tolerance: int = 0,
) -> str:
    """
    核对数据库库存(stock_count) vs 鲸芽导出Excel库存(可售库存)，按 skuid 匹配。

    - stock_mismatch：两边都有数据，但库存数量差异 > tolerance
    - missing_in_jingya_export：数据库里已绑定渠道的 skuid，但在最新鲸芽导出里完全找不到
      （可能已在鲸芽端被删除/解绑）
    - missing_in_db：鲸芽导出里有库存数据的 skuid，但数据库里没有对应记录
      （可能未导入/未绑定成功）

    鲸芽导出中"未铺货"的商品通常"可售库存"为空，视为无可比数据，不计入 mismatch。

    jingya_excel_path 不传时，自动去 GEI_EXPORT_BASE/<品牌>/ 下查找最新的 GEI*.xlsx。
    """
    if jingya_excel_path is None:
        jingya_excel_path = _find_latest_gei_excel(brand)

    df_db = _fetch_db_stock(brand)
    df_xy = _read_jingya_stock_excel(
        jingya_excel_path=jingya_excel_path,
        excel_skuid_col=excel_skuid_col,
        excel_stock_col=excel_stock_col,
        excel_title_col=excel_title_col,
        excel_status_col=excel_status_col,
    )

    merged = df_db.merge(df_xy, on="skuid", how="outer", indicator=True)

    merged["final_title"] = merged["product_title"].fillna("").astype(str).str.strip()
    empty_mask = merged["final_title"] == ""
    merged.loc[empty_mask, "final_title"] = merged.loc[empty_mask, "excel_channel_title"].fillna("")

    # 数据库有绑定，但鲸芽导出里完全没有这个 skuid
    df_missing_in_excel = merged[merged["_merge"] == "left_only"].copy()

    # 鲸芽导出里有库存数据，但数据库没有该 skuid
    df_missing_in_db = merged[
        (merged["_merge"] == "right_only") & merged["jy_stock"].notna()
    ].copy()

    # 两边都有的，且鲸芽库存有效数值（排除未铺货导致的空库存）
    both = merged[merged["_merge"] == "both"].copy()
    both = both[both["jy_stock"].notna()]
    both["diff"] = both["jy_stock"] - both["stock_count"]

    df_mismatch = both[both["diff"].abs() > tolerance].copy()

    print(f"[CHECK] 数据库已绑定SKU: {len(df_db)} | 鲸芽导出SKU: {len(df_xy)}")
    print(f"[CHECK] 可比对SKU(双方都有且鲸芽有库存数值): {len(both)}")
    print(f"[CHECK] 库存不一致: {len(df_mismatch)}")
    print(f"[CHECK] 数据库有绑定但鲸芽导出中找不到: {len(df_missing_in_excel)}")
    print(f"[CHECK] 鲸芽导出中有库存但数据库无记录: {len(df_missing_in_db)}")

    if output_report_path is None:
        brand_l = brand.lower().strip()
        base_dir = BRAND_CONFIG[brand_l].get("BASE")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(base_dir) / "document" / "stock_check" if base_dir else Path(".")
        output_report_path = str(out_dir / f"{brand_l}_stock_diff_{ts}.xlsx")

    return _export_stock_diff_report(df_mismatch, df_missing_in_excel, df_missing_in_db, output_report_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="核对数据库库存 vs 鲸芽导出Excel库存（按 skuid 匹配）")
    parser.add_argument("--brand", required=True, help="品牌名，例如 clarks / camper / geox / ecco / barbour")
    parser.add_argument(
        "--excel", default=None,
        help="可选，手动指定鲸芽导出Excel路径；不填则自动去 GEI_EXPORT_BASE/<品牌>/ 下查找最新的 GEI*.xlsx",
    )
    parser.add_argument("--output", default=None, help="可选，差异报告输出路径（默认按品牌路径自动生成）")
    parser.add_argument("--tolerance", type=int, default=0, help="允许的库存差异容忍值，默认0（严格相等）")
    args = parser.parse_args()

    check_jingya_stock_mismatch(
        brand=args.brand,
        jingya_excel_path=args.excel,
        output_report_path=args.output,
        tolerance=args.tolerance,
    )
