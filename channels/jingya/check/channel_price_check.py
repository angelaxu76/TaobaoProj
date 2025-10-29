import psycopg2
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime

from config import BRAND_CONFIG, PGSQL_CONFIG, BARBOUR

###############################################################################
# 公共小工具
###############################################################################

def _get_pg_conn_and_table(brand: str):
    """
    根据品牌拿到：
    - psycopg2连接对象
    - 该品牌对应的表名
    """
    brand_l = brand.lower().strip()
    if brand_l not in BRAND_CONFIG:
        raise ValueError(f"未知品牌: {brand}")

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


###############################################################################
# ================ 1) 鲸芽价一致性检查（skuid 对齐） ==========================
###############################################################################

def _fetch_brand_inventory_for_jingya(brand: str) -> pd.DataFrame:
    """
    从数据库读取用于“鲸芽价一致性检查”的列
    匹配粒度：skuid
    """
    conn, table_name = _get_pg_conn_and_table(brand)

    sql = f"""
        SELECT
            skuid,
            channel_product_id,
            product_code,
            product_title,
            jingya_untaxed_price,
            taobao_store_price
        FROM {table_name}
        WHERE skuid IS NOT NULL
          AND TRIM(skuid) <> ''
    """

    df_db = pd.read_sql(sql, conn)
    conn.close()

    # 清洗
    df_db["skuid"] = df_db["skuid"].astype(str).str.strip()
    df_db["product_title"] = df_db["product_title"].fillna("").astype(str).str.strip()

    for col in ["jingya_untaxed_price", "taobao_store_price"]:
        df_db[col] = pd.to_numeric(df_db[col], errors="coerce")

    return df_db


def _read_jingya_excel(
    jingya_excel_path: str,
    excel_skuid_col: str,
    excel_price_col: str,
    excel_title_col: str,
) -> pd.DataFrame:
    """
    读取鲸芽导出的SKU表：
    - skuID                      -> skuid
    - 通用渠道价格（未税）        -> jy_excel_price
    - 渠道产品名称               -> excel_channel_title
    """
    df_xy = pd.read_excel(jingya_excel_path)

    # 列名规格化（去空格等）
    cols_normalized = {c: str(c).strip() for c in df_xy.columns}
    df_xy.rename(columns=cols_normalized, inplace=True)

    # 宽松匹配列名（允许大小写/空格差异）
    def _find_col(want: str, cols) -> Optional[str]:
        if want in cols:
            return want
        want_norm = want.replace(" ", "").lower()
        for c in cols:
            if str(c).replace(" ", "").lower() == want_norm:
                return c
        return None

    mapping_spec = {
        excel_skuid_col: "skuid",
        excel_price_col: "jy_excel_price",
        excel_title_col: "excel_channel_title",
    }

    final_map = {}
    for want_src, std_name in mapping_spec.items():
        real_col = _find_col(want_src, df_xy.columns)
        if real_col is None:
            raise KeyError(f"鲸芽Excel中缺少列: {want_src}")
        final_map[real_col] = std_name

    df_xy = df_xy.rename(columns=final_map)

    keep_cols = ["skuid", "jy_excel_price", "excel_channel_title"]
    df_xy = df_xy[keep_cols].copy()

    # 清洗
    df_xy["skuid"] = df_xy["skuid"].astype(str).str.strip()
    df_xy["excel_channel_title"] = df_xy["excel_channel_title"].fillna("").astype(str).str.strip()
    df_xy["jy_excel_price"] = pd.to_numeric(df_xy["jy_excel_price"], errors="coerce")

    return df_xy


def _export_jingya_diff_report(df_bad: pd.DataFrame, output_report_path: str) -> str:
    """
    导出鲸芽价差异报告
    """
    out_path = Path(output_report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ordered_cols = [
        "channel_product_id",
        "skuid",
        "product_code",
        "final_title",
        "jingya_untaxed_price",
        "jy_excel_price",
        "taobao_store_price",
        "diff",
        "diff_pct",
    ]

    for c in ordered_cols:
        if c not in df_bad.columns:
            df_bad[c] = None

    df_out = df_bad[ordered_cols].copy()

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="price_mismatch")

    print(f"[OK] 鲸芽价不同步SKU导出: {out_path}")
    return str(out_path)


def check_jingya_price_mismatch(
    brand: str,
    jingya_excel_path: str,
    output_report_path: str,
    excel_skuid_col: str = "skuID",
    excel_price_col: str = "通用渠道价格（未税）",
    excel_title_col: str = "渠道产品名称",
    tolerance: float = 0.5,
) -> str:
    """
    检查鲸芽平台价 vs 我们数据库价 (按 skuid)。
    把差异超过 tolerance 的SKU导出。
    """
    df_db = _fetch_brand_inventory_for_jingya(brand)
    df_xy = _read_jingya_excel(
        jingya_excel_path=jingya_excel_path,
        excel_skuid_col=excel_skuid_col,
        excel_price_col=excel_price_col,
        excel_title_col=excel_title_col,
    )

    merged = df_db.merge(df_xy, on="skuid", how="inner")

    # title: DB优先，否则用鲸芽渠道产品名称
    merged["final_title"] = merged["product_title"].fillna("").astype(str).str.strip()
    empty_mask = merged["final_title"] == ""
    merged.loc[empty_mask, "final_title"] = (
        merged.loc[empty_mask, "excel_channel_title"].fillna("").astype(str).str.strip()
    )

    # 差异
    merged["diff"] = merged["jy_excel_price"] - merged["jingya_untaxed_price"]
    merged["diff_abs"] = merged["diff"].abs()
    merged["diff_pct"] = merged.apply(
        lambda r: (r["diff"] / r["jingya_untaxed_price"])
        if pd.notnull(r["jingya_untaxed_price"]) and r["jingya_untaxed_price"] not in [0, 0.0]
        else None,
        axis=1
    )

    # 只要价差超过 tolerance 的
    bad = merged[
        (merged["diff_abs"] > tolerance)
        & pd.notnull(merged["jy_excel_price"])
        & pd.notnull(merged["jingya_untaxed_price"])
    ].copy()

    if bad.empty:
        print("[INFO] 鲸芽价已全部同步✅")
        return _export_jingya_diff_report(bad, output_report_path)

    return _export_jingya_diff_report(bad, output_report_path)


###############################################################################
# ================ 2) 淘宝安全线检查（product_code+size 对齐） ================
###############################################################################

def _fetch_brand_inventory_for_taobao(brand: str) -> pd.DataFrame:
    """
    从数据库读取用于“淘宝安全线检查”的列
    匹配粒度：product_code + size
    """
    conn, table_name = _get_pg_conn_and_table(brand)

    sql = f"""
        SELECT
            product_code,
            size,
            jingya_untaxed_price,
            channel_product_id,
            skuid,
            product_title
        FROM {table_name}
        WHERE product_code IS NOT NULL
          AND TRIM(product_code) <> ''
          AND size IS NOT NULL
          AND TRIM(size) <> ''
    """

    df_db = pd.read_sql(sql, conn)
    conn.close()

    df_db["product_code"] = df_db["product_code"].astype(str).str.strip()
    df_db["size"] = df_db["size"].astype(str).str.strip()
    df_db["product_title"] = df_db["product_title"].fillna("").astype(str).str.strip()
    df_db["jingya_untaxed_price"] = pd.to_numeric(df_db["jingya_untaxed_price"], errors="coerce")

    return df_db


def _read_taobao_excel(
    taobao_excel_path: str,
    excel_spec_col: str = "sku规格",
    excel_price_col: str = "sku销售价",
    excel_title_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    读取淘宝导出的SKU表：
    - sku规格: 'LQU1849SG71,4,' -> product_code='LQU1849SG71', size='4'
    - sku销售价: 当前淘宝售价
    - (可选)商品标题列：补title用
    """
    df_tb = pd.read_excel(taobao_excel_path)

    cols_norm = {c: str(c).strip() for c in df_tb.columns}
    df_tb.rename(columns=cols_norm, inplace=True)

    if excel_spec_col not in df_tb.columns:
        raise KeyError(f"淘宝Excel缺少列 {excel_spec_col}")
    if excel_price_col not in df_tb.columns:
        raise KeyError(f"淘宝Excel缺少列 {excel_price_col}")

    use_cols = [excel_spec_col, excel_price_col]
    if excel_title_col and excel_title_col in df_tb.columns:
        use_cols.append(excel_title_col)

    df_tb = df_tb[use_cols].copy()

    def parse_spec(raw: str):
        # 'LQU1849SG71,4,' -> ['LQU1849SG71','4']
        if pd.isna(raw):
            return "", ""
        s = str(raw).strip().strip(",")
        parts = [p.strip() for p in s.split(",") if p.strip() != ""]
        if len(parts) == 0:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    df_tb["product_code"], df_tb["size"] = zip(*df_tb[excel_spec_col].map(parse_spec))

    df_tb["product_code"] = df_tb["product_code"].astype(str).str.strip()
    df_tb["size"] = df_tb["size"].astype(str).str.strip()
    df_tb["taobao_price_excel"] = pd.to_numeric(df_tb[excel_price_col], errors="coerce")

    if excel_title_col and excel_title_col in df_tb.columns:
        df_tb["taobao_excel_title"] = df_tb[excel_title_col].fillna("").astype(str).str.strip()
    else:
        df_tb["taobao_excel_title"] = ""

    df_tb = df_tb[["product_code", "size", "taobao_price_excel", "taobao_excel_title"]]

    df_tb = df_tb[(df_tb["product_code"] != "") & (df_tb["size"] != "")]
    df_tb = df_tb.dropna(subset=["taobao_price_excel"])

    return df_tb


def _export_taobao_risk_report(df_bad: pd.DataFrame, output_report_path: str) -> str:
    """
    导出淘宝倒挂风险报告
    """
    out_path = Path(output_report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ordered_cols = [
        "product_code",
        "size",
        "final_title",
        "jingya_untaxed_price",
        "safe_min_price",
        "taobao_price_excel",
        "gap",
        "channel_product_id",
        "skuid",
    ]

    for c in ordered_cols:
        if c not in df_bad.columns:
            df_bad[c] = None

    df_out = df_bad[ordered_cols].copy()

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="taobao_risk")

    print(f"[OK] 淘宝倒挂风险SKU导出: {out_path}")
    return str(out_path)


def check_taobao_margin_safety(
    brand: str,
    taobao_excel_path: str,
    output_report_path: str,
    safety_multiplier: float = 1.4,
    excel_spec_col: str = "sku规格",
    excel_price_col: str = "sku销售价",
    excel_title_col: Optional[str] = None,
) -> str:
    """
    检查淘宝售价是否 >= jingya_untaxed_price * safety_multiplier (默认1.4 = 40%)。
    匹配粒度：product_code + size
    导出不达标SKU（可能倒挂）。
    """
    df_db = _fetch_brand_inventory_for_taobao(brand)
    df_tb = _read_taobao_excel(
        taobao_excel_path=taobao_excel_path,
        excel_spec_col=excel_spec_col,
        excel_price_col=excel_price_col,
        excel_title_col=excel_title_col,
    )

    merged = df_db.merge(df_tb, on=["product_code", "size"], how="inner")

    merged["safe_min_price"] = merged["jingya_untaxed_price"] * safety_multiplier
    merged["gap"] = merged["safe_min_price"] - merged["taobao_price_excel"]

    merged["final_title"] = merged["product_title"].fillna("").astype(str).str.strip()
    mask_empty = merged["final_title"] == ""
    merged.loc[mask_empty, "final_title"] = merged.loc[mask_empty, "taobao_excel_title"]

    risky = merged[
        pd.notnull(merged["jingya_untaxed_price"])
        & pd.notnull(merged["taobao_price_excel"])
        & (merged["taobao_price_excel"] < merged["safe_min_price"])
    ].copy()

    if risky.empty:
        print("[INFO] 淘宝端全部≥安全线✅")
        return _export_taobao_risk_report(risky, output_report_path)

    return _export_taobao_risk_report(risky, output_report_path)


###############################################################################
# 简单的一键跑（给 Barbour 用）
###############################################################################

def run_barbour_jingya_check():
    """
    Barbour：鲸芽价同步检查
    """
    jingya_excel_path = r"D:\Downloads\GEI@sales_catalogue_export@251029221824@1313.xlsx"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(BARBOUR["BASE"]) / "document" / "price_check" / f"barbour_price_diff_{ts}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    check_jingya_price_mismatch(
        brand="barbour",
        jingya_excel_path=jingya_excel_path,
        output_report_path=str(out_path),
        tolerance=0.5,
    )


def run_barbour_taobao_check():
    """
    Barbour：淘宝倒挂风险检查
    """
    taobao_excel_path = r"D:\Downloads\taobao_sku_price.xlsx"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(BARBOUR["BASE"]) / "document" / "price_check" / f"barbour_taobao_risk_{ts}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    check_taobao_margin_safety(
        brand="barbour",
        taobao_excel_path=taobao_excel_path,
        output_report_path=str(out_path),
        safety_multiplier=1.4,
        excel_spec_col="sku规格",
        excel_price_col="sku销售价",
        excel_title_col=None,  # 如果淘宝Excel有标题列，比如"商品名称"，把名字填这里
    )


if __name__ == "__main__":
    run_barbour_jingya_check()
    run_barbour_taobao_check()
