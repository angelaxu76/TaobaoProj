import datetime as dt
from typing import Optional, Union

import pandas as pd
import psycopg2

from config import PGSQL_CONFIG  # 你现有的配置


DateLike = Union[str, dt.date]


def _normalize_date(d: DateLike) -> dt.date:
    """把字符串或 date 统一转成 date 对象。"""
    if isinstance(d, dt.date):
        return d
    return dt.datetime.strptime(d, "%Y-%m-%d").date()


def fetch_order_poe_data(conn, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """
    从 export_shipments 中取出指定日期范围内的订单/POE记录。
    表结构见 create_export_shipments_table.sql：
    - supplier_order_no TEXT
    - supplier_name TEXT
    - skuid TEXT
    - quantity INTEGER
    - poe_id TEXT
    - poe_date DATE
    - purchase_unit_cost_gbp NUMERIC(18,4)
    """
    sql = """
        SELECT
            -- 清洗订单号，去掉小数点后面的 .0（防止历史数据里存成 "1300009326.0" 这种）
            CASE
                WHEN supplier_order_no IS NULL THEN NULL
                WHEN supplier_order_no ~ '\\.0$'
                    THEN regexp_replace(supplier_order_no, '\\.0$', '')
                ELSE supplier_order_no
            END AS supplier_order_no,
            supplier_name,
            skuid,
            quantity,
            poe_id,
            poe_date::date AS poe_date,
            purchase_unit_cost_gbp::numeric AS purchase_unit_cost_gbp
        FROM export_shipments
        WHERE poe_date::date BETWEEN %(start_date)s AND %(end_date)s
          AND supplier_order_no IS NOT NULL
    """

    df = pd.read_sql(sql, conn, params={"start_date": start_date, "end_date": end_date})
    return df


def build_anna_note_for_group(
    order_no: str,
    supplier_name: str,
    poe_rows: pd.DataFrame,
    total_cost_gbp: Optional[float] = None,
) -> str:
    """
    为某个 supplier_order_no + supplier_name 生成 ANNA Note 文本。

    poe_rows 至少包含列：poe_id, poe_date, skuid, quantity, purchase_unit_cost_gbp

    新增：
    - 在 supplier 行后面显示该订单的总金额 total_cost_gbp；
    - 在每个 POE 的 SKUID 列表中，附带显示该 SKUID 的 purchase_unit_cost_gbp 单价。
    """
    import datetime as _dt

    lines = []
    # 第一行：订单号
    lines.append(f"order number：{order_no}")

    # 第二行：供应商 + 总金额（如果有）
    if total_cost_gbp is not None:
        try:
            total_cost_gbp = float(total_cost_gbp)
            lines.append(
                f"supplier：{supplier_name}，Total Purchase Cost (GBP)：{total_cost_gbp:.2f}"
            )
        except Exception:
            # 万一转换失败，就退回到只显示 supplier
            lines.append(f"supplier：{supplier_name}")
    else:
        lines.append(f"supplier：{supplier_name}")

    poe_rows_clean = poe_rows.dropna(subset=["poe_id"]).copy()

    if poe_rows_clean.empty:
        lines.append("1， POE: 无对应POE记录，CI: 无，POE Date：无")
        return "\n".join(lines)

    # 排序后按 (poe_id, poe_date) 分组
    poe_rows_sorted = poe_rows_clean.sort_values(
        ["poe_date", "poe_id", "skuid"],
        na_position="last"
    )

    for idx, ((poe_id, poe_date), sub_df) in enumerate(
        poe_rows_sorted.groupby(["poe_id", "poe_date"]),
        start=1
    ):
        # CI 文件名按你的规则：CommercialInvoice_PoE_<poe_id>.pdf
        ci_filename = f"CommercialInvoice_PoE_{poe_id}.pdf"

        # POE 日期格式化
        if isinstance(poe_date, _dt.date):
            poe_date_str = poe_date.strftime("%Y-%m-%d")
        elif poe_date is None:
            poe_date_str = ""
        else:
            try:
                poe_date_parsed = _dt.datetime.strptime(str(poe_date), "%Y-%m-%d").date()
                poe_date_str = poe_date_parsed.strftime("%Y-%m-%d")
            except Exception:
                poe_date_str = str(poe_date)

        # === 新逻辑：汇总 SKUID + 单价 ===
        # 保证有 skuid 和 purchase_unit_cost_gbp
        sku_price_df = (
            sub_df[["skuid", "purchase_unit_cost_gbp"]]
            .dropna(subset=["skuid"])
            .copy()
        )
        if not sku_price_df.empty:
            sku_price_df["skuid"] = sku_price_df["skuid"].astype(str)
            # 同一个 SKUID 只保留一条记录
            sku_price_df = sku_price_df.sort_values(["skuid"])
            sku_price_df = sku_price_df.drop_duplicates(subset=["skuid"], keep="first")

            skuid_parts = []
            for _, row in sku_price_df.iterrows():
                sk = row["skuid"]
                price_val = row["purchase_unit_cost_gbp"]
                try:
                    price_float = float(price_val)
                    price_str = f"£{price_float:.2f}"
                except Exception:
                    price_str = str(price_val)
                # 形如：26176998(£79.20)
                skuid_parts.append(f"{sk} ({price_str})")

            skuid_str = ", ".join(skuid_parts)
        else:
            skuid_str = ""

        # 汇总件数：sum(quantity)
        total_qty = (
            sub_df["quantity"]
            .fillna(0)
            .astype(float)
            .sum()
        )
        # 转成 int 显示
        try:
            total_qty_int = int(total_qty)
        except Exception:
            total_qty_int = total_qty

        # 行内容：POE + SKUID(带单价) + 件数 + CI + 日期
        line = (
            f"{idx}， POE: {poe_id}，"
            f"SKUID: {skuid_str}，"
            f"Items: {total_qty_int}，"
            f"CI: {ci_filename}，"
            f"POE Date：{poe_date_str}"
        )
        lines.append(line)

    return "\n".join(lines)


def generate_supplier_orders_excel(
    start_date: DateLike,
    end_date: DateLike,
    output_path: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> str:
    """
    核心函数：供 pipeline 直接调用。

    参数：
        start_date: 开始日期，'YYYY-MM-DD' 或 datetime.date
        end_date  : 结束日期，'YYYY-MM-DD' 或 datetime.date
        output_path: 输出 Excel 路径
        conn: 可选，如果 pipeline 已有 psycopg2 连接可以传进来；
              如果为 None，则函数内部自行创建并关闭连接。

    返回：
        实际写出的 Excel 文件路径（即 output_path）
    """
    start_date = _normalize_date(start_date)
    end_date = _normalize_date(end_date)

    own_conn = False
    if conn is None:
        conn = psycopg2.connect(**PGSQL_CONFIG)
        own_conn = True

    try:
        df = fetch_order_poe_data(conn, start_date, end_date)
    finally:
        if own_conn:
            conn.close()

    if df.empty:
        print(f"[INFO] {start_date} ~ {end_date} 范围内没有匹配的 export_shipments 记录。")
        # 仍然创建一个空的 Excel，避免 pipeline 报错
        empty_df = pd.DataFrame(
            columns=[
                "Supplier Order No",
                "Supplier Name",
                "Total Purchase Cost (GBP)",
                "Items Count",   # 总件数
                "POE Date",
                "ANNA Note",
            ]
        )
        empty_df.to_excel(output_path, index=False)
        return output_path

    # 填充 NaN，避免后面处理麻烦
    df["purchase_unit_cost_gbp"] = df["purchase_unit_cost_gbp"].fillna(0)
    df["quantity"] = df["quantity"].fillna(0)

    result_rows = []

    # 以 supplier_order_no + supplier_name 为粒度分组
    group_cols = ["supplier_order_no", "supplier_name"]
    for (order_no, supplier_name), group in df.groupby(group_cols):
        if order_no is None:
            continue

        # 总采购成本：所有行的 purchase_unit_cost_gbp 求和
        # 这里保持与你之前的逻辑一致
        total_cost = group["purchase_unit_cost_gbp"].sum()

        # 总件数：sum(quantity)
        items_count = int(group["quantity"].astype(float).sum())

        # 生成 ANNA Note 文本（传入 POE + SKUID + quantity + 单价 + 总金额）
        anna_note = build_anna_note_for_group(
            order_no=order_no,
            supplier_name=supplier_name,
            poe_rows=group[[
                "poe_id",
                "poe_date",
                "skuid",
                "quantity",
                "purchase_unit_cost_gbp",
            ]],
            total_cost_gbp=float(total_cost),
        )

        # 为该订单计算一个汇总 POE 日期（取最早的 POE 日期）
        poe_dates = group["poe_date"].dropna().unique()
        if len(poe_dates) > 0:
            poe_dates_sorted = sorted(
                [
                    d if isinstance(d, dt.date) else dt.datetime.strptime(str(d), "%Y-%m-%d").date()
                    for d in poe_dates
                ]
            )
            poe_date_final = poe_dates_sorted[0]
            poe_date_str = poe_date_final.strftime("%Y-%m-%d")
        else:
            poe_date_str = ""

        result_rows.append({
            "Supplier Order No": order_no,
            "Supplier Name": supplier_name,
            "Total Purchase Cost (GBP)": round(float(total_cost), 2),
            "Items Count": items_count,   # 这一单一共寄出了多少件
            "POE Date": poe_date_str,
            "ANNA Note": anna_note,
        })

    result_df = pd.DataFrame(result_rows)

    # 按 Supplier Name + Supplier Order No 排序
    result_df = result_df.sort_values(["Supplier Name", "Supplier Order No"])

    # 写 Excel
    result_df.to_excel(output_path, index=False)
    print(f"[OK] 已生成 Excel：{output_path}")
    return output_path

# =========================
# V2: join ANNA transactions
# 不影响 V1：仅新增函数
# =========================

def fetch_anna_order_summary(conn, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """
    从 anna_transactions 汇总订单的交易信息（按 order_number）。
    说明：
    - 这里按 authorised_on 的日期范围过滤（与你 v1 的 poe_date 范围类似）
    - 如果你希望“只要订单号匹配就汇总全部历史交易”，可以去掉日期过滤条件
    """
    sql = """
        SELECT
            -- 清洗订单号：去掉 .0，保持与 export_shipments 逻辑一致
            CASE
                WHEN order_number IS NULL THEN NULL
                WHEN order_number::text ~ '\\.0$'
                    THEN regexp_replace(order_number::text, '\\.0$', '')
                ELSE order_number::text
            END AS order_number,

            COUNT(*) AS anna_txn_count,
            ROUND(SUM(amount)::numeric, 2) AS anna_total_amount_gbp,
            MIN(authorised_on)::date AS anna_first_authorised_date,

            STRING_AGG(DISTINCT COALESCE(anna_category,''), ', ' ORDER BY COALESCE(anna_category,'')) AS anna_categories,
            STRING_AGG(DISTINCT COALESCE(counterparty,''), ', ' ORDER BY COALESCE(counterparty,'')) AS anna_counterparties

        FROM public.anna_transactions
        WHERE order_number IS NOT NULL
          AND authorised_on::date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY 1
    """
    return pd.read_sql(sql, conn, params={"start_date": start_date, "end_date": end_date})


def generate_supplier_orders_excel_v2(
    start_date: DateLike,
    end_date: DateLike,
    output_path: str,
    conn: Optional[psycopg2.extensions.connection] = None,
    diff_threshold_gbp: float = 5.0,
) -> str:
    """
    V2 版本：在 V1 供应商订单汇总基础上，按 order number join ANNA 交易汇总。

    新增列（核心）：
    - ANNA Txn Count / ANNA Total Amount / ANNA First Authorised Date
    - ANNA Categories / ANNA Counterparties
    - Has POE / Amount Diff (ANNA - POE) / Need Review

    diff_threshold_gbp:
        用于 Need Review 判断阈值（默认 5 镑）
    """
    start_date = _normalize_date(start_date)
    end_date = _normalize_date(end_date)

    own_conn = False
    if conn is None:
        conn = psycopg2.connect(**PGSQL_CONFIG)
        own_conn = True

    try:
        # === 1) 复用 V1 的 POE 数据抓取 ===
        df = fetch_order_poe_data(conn, start_date, end_date)

        # === 2) 取 ANNA 汇总（按订单号） ===
        anna_sum = fetch_anna_order_summary(conn, start_date, end_date)
    finally:
        if own_conn:
            conn.close()

    # 如果 export_shipments 没数据，仍输出空表（保持 pipeline 稳定）
    if df.empty:
        empty_df = pd.DataFrame(
            columns=[
                "Supplier Order No",
                "Supplier Name",
                "Total Purchase Cost (GBP)",
                "Items Count",
                "POE Date",
                "ANNA Note",

                # V2 新列
                "ANNA Txn Count",
                "ANNA Total Amount (GBP)",
                "ANNA First Authorised Date",
                "ANNA Categories",
                "ANNA Counterparties",
                "Has POE",
                "Amount Diff (ANNA - POE)",
                "Need Review",
            ]
        )
        empty_df.to_excel(output_path, index=False)
        print(f"[OK] 已生成 Excel（空表）：{output_path}")
        return output_path

    # 填充 NaN，避免后面处理麻烦（保持与 V1 一致）:contentReference[oaicite:3]{index=3}
    df["purchase_unit_cost_gbp"] = df["purchase_unit_cost_gbp"].fillna(0)
    df["quantity"] = df["quantity"].fillna(0)

    # === 3) 先按 V1 的逻辑生成 supplier notes 基础结果 ===
    result_rows = []
    group_cols = ["supplier_order_no", "supplier_name"]
    for (order_no, supplier_name), group in df.groupby(group_cols):
        if order_no is None:
            continue

        total_cost = group["purchase_unit_cost_gbp"].sum()
        items_count = int(group["quantity"].astype(float).sum())

        anna_note = build_anna_note_for_group(
            order_no=order_no,
            supplier_name=supplier_name,
            poe_rows=group[[
                "poe_id",
                "poe_date",
                "skuid",
                "quantity",
                "purchase_unit_cost_gbp",
            ]],
            total_cost_gbp=float(total_cost),
        )

        poe_dates = group["poe_date"].dropna().unique()
        if len(poe_dates) > 0:
            poe_dates_sorted = sorted(
                [
                    d if isinstance(d, dt.date) else dt.datetime.strptime(str(d), "%Y-%m-%d").date()
                    for d in poe_dates
                ]
            )
            poe_date_final = poe_dates_sorted[0]
            poe_date_str = poe_date_final.strftime("%Y-%m-%d")
        else:
            poe_date_str = ""

        result_rows.append({
            "Supplier Order No": order_no,
            "Supplier Name": supplier_name,
            "Total Purchase Cost (GBP)": round(float(total_cost), 2),
            "Items Count": items_count,
            "POE Date": poe_date_str,
            "ANNA Note": anna_note,
        })

    result_df = pd.DataFrame(result_rows)

    # === 4) join ANNA 汇总 ===
    # 对齐字段名
    if not anna_sum.empty:
        anna_sum = anna_sum.rename(columns={
            "anna_txn_count": "ANNA Txn Count",
            "anna_total_amount_gbp": "ANNA Total Amount (GBP)",
            "anna_first_authorised_date": "ANNA First Authorised Date",
            "anna_categories": "ANNA Categories",
            "anna_counterparties": "ANNA Counterparties",
        })

    result_df = result_df.merge(
        anna_sum,
        how="left",
        left_on="Supplier Order No",
        right_on="order_number",
    ).drop(columns=["order_number"], errors="ignore")

    # --- 兜底：保证 V2 新列一定存在，避免 KeyError ---
    for col in ["ANNA Txn Count", "ANNA Total Amount (GBP)", "ANNA First Authorised Date",
                "ANNA Categories", "ANNA Counterparties"]:
        if col not in result_df.columns:
            result_df[col] = pd.NA


    # === 5) 计算判断列（你想要的一眼识别） ===
    # Has POE：只要 POE Date 有值就算出口/有POE
    result_df["Has POE"] = result_df["POE Date"].astype(str).str.len().gt(0)

    # 金额差异：ANNA总额 - POE总成本
    result_df["Amount Diff (ANNA - POE)"] = (
        result_df["ANNA Total Amount (GBP)"].fillna(0) - result_df["Total Purchase Cost (GBP)"].fillna(0)
    ).round(2)

    # Need Review：有 POE 且差异超过阈值 或者 有订单但缺 ANNA 记录（你可按需要再加规则）
    result_df["Need Review"] = (
        (result_df["Has POE"] == True) &
        (
            (result_df["ANNA Total Amount (GBP)"].isna()) |
            (result_df["Amount Diff (ANNA - POE)"].abs() >= float(diff_threshold_gbp))
        )
    )

    # 排序：保持你原来的习惯
    result_df = result_df.sort_values(["Supplier Name", "Supplier Order No"])

    # 写 Excel
    result_df.to_excel(output_path, index=False)
    print(f"[OK] 已生成 V2 Excel：{output_path}")
    return output_path
# =========================
# V3: ANNA as MAIN, join POE summary
# 不影响 V1/V2：仅新增函数
# =========================

def fetch_anna_orders_main(conn, start_date: dt.date, end_date: dt.date, filter_by_date: bool = False) -> pd.DataFrame:
    """
    ANNA 主表（按订单号聚合）。
    filter_by_date=False：默认不按日期过滤（更符合“ANNA全量→找没POE订单”的需求）
    """
    date_filter_sql = ""
    params = {}

    if filter_by_date:
        date_filter_sql = "AND authorised_on::date BETWEEN %(start_date)s AND %(end_date)s"
        params = {"start_date": start_date, "end_date": end_date}

    sql = f"""
        SELECT
            CASE
                WHEN order_number IS NULL THEN NULL
                WHEN order_number::text ~ '\\.0$'
                    THEN regexp_replace(order_number::text, '\\.0$', '')
                ELSE order_number::text
            END AS order_number,

            COUNT(*) AS anna_txn_count,
            MIN(authorised_on)::date AS anna_first_authorised_date,

            ROUND(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END))::numeric, 2) AS anna_purchase_amount_gbp,
            ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)::numeric, 2) AS anna_refund_amount_gbp,
            ROUND(
                (ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END))
                 - SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END))::numeric, 2
            ) AS anna_net_amount_gbp,

            STRING_AGG(DISTINCT COALESCE(anna_category,''), ', ' ORDER BY COALESCE(anna_category,'')) AS anna_categories,
            STRING_AGG(DISTINCT COALESCE(counterparty,''), ', ' ORDER BY COALESCE(counterparty,'')) AS anna_counterparties

        FROM public.anna_transactions
        WHERE order_number IS NOT NULL
        {date_filter_sql}
        GROUP BY 1
    """
    return pd.read_sql(sql, conn, params=params or None)


def fetch_poe_summary_by_order(conn, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """
    POE 汇总（按 poe_date 过滤时间窗）。
    """
    sql = """
        SELECT
            CASE
                WHEN supplier_order_no IS NULL THEN NULL
                WHEN supplier_order_no ~ '\\.0$'
                    THEN regexp_replace(supplier_order_no, '\\.0$', '')
                ELSE supplier_order_no
            END AS order_number,

            MIN(supplier_name) AS supplier_name,
            MIN(poe_date)::date AS first_poe_date,
            COUNT(DISTINCT poe_id) AS poe_count,
            STRING_AGG(DISTINCT poe_id, ', ' ORDER BY poe_id) AS poe_ids,

            SUM(COALESCE(quantity,0))::int AS items_count,
            ROUND(SUM(COALESCE(purchase_unit_cost_gbp,0))::numeric, 2) AS poe_total_export_amount_gbp
        FROM public.export_shipments
        WHERE poe_date::date BETWEEN %(start_date)s AND %(end_date)s
          AND supplier_order_no IS NOT NULL
        GROUP BY 1
    """
    return pd.read_sql(sql, conn, params={"start_date": start_date, "end_date": end_date})


def generate_supplier_orders_excel_v3(
    start_date: DateLike,
    end_date: DateLike,
    output_path: str,
    conn: Optional[psycopg2.extensions.connection] = None,
    diff_threshold_gbp: float = 5.0,
    coverage_full_threshold: float = 0.98,
    anna_filter_by_date: bool = False,  # ✅ 默认 False：ANNA 全量主表
    debug: bool = True                  # ✅ 默认 True：打印自检信息
) -> str:
    start_date = _normalize_date(start_date)
    end_date = _normalize_date(end_date)

    own_conn = False
    if conn is None:
        conn = psycopg2.connect(**PGSQL_CONFIG)
        own_conn = True

    try:
        # ---------- 自检：看原表在这个窗里有没有数据 ----------
        if debug:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.anna_transactions;")
                total_anna = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM public.anna_transactions WHERE order_number IS NOT NULL;")
                anna_with_order = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM public.anna_transactions WHERE authorised_on::date BETWEEN %s AND %s;",
                    (start_date, end_date)
                )
                anna_in_range = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM public.anna_transactions WHERE order_number IS NOT NULL AND authorised_on::date BETWEEN %s AND %s;",
                    (start_date, end_date)
                )
                anna_with_order_in_range = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(DISTINCT supplier_order_no) FROM public.export_shipments WHERE poe_date::date BETWEEN %s AND %s AND supplier_order_no IS NOT NULL;",
                    (start_date, end_date)
                )
                poe_orders_in_range = cur.fetchone()[0]

            print(f"[DEBUG] anna_transactions total rows: {total_anna}")
            print(f"[DEBUG] anna_transactions rows with order_number: {anna_with_order}")
            print(f"[DEBUG] anna_transactions rows in date range({start_date}~{end_date}): {anna_in_range}")
            print(f"[DEBUG] anna_transactions rows with order_number in date range: {anna_with_order_in_range}")
            print(f"[DEBUG] export_shipments distinct orders in poe_date range: {poe_orders_in_range}")

        # ---------- 取汇总 ----------
        anna_main = fetch_anna_orders_main(conn, start_date, end_date, filter_by_date=anna_filter_by_date)
        poe_sum = fetch_poe_summary_by_order(conn, start_date, end_date)

    finally:
        if own_conn:
            conn.close()

    if debug:
        print(f"[DEBUG] anna_main orders: {len(anna_main)}")
        print(f"[DEBUG] poe_sum orders: {len(poe_sum)}")

    # ANNA 主表 left join POE
    result_df = anna_main.merge(poe_sum, how="left", on="order_number")

    if debug:
        print(f"[DEBUG] merged rows: {len(result_df)}")

    # 如果还是空，就输出空表但带列（避免你误以为没生成）
    if result_df.empty:
        cols = [
            "Order Number",
            "ANNA Txn Count",
            "ANNA First Authorised Date",
            "ANNA Purchase Amount (GBP)",
            "ANNA Refund Amount (GBP)",
            "ANNA Net Amount (GBP)",
            "ANNA Categories",
            "ANNA Counterparties",
            "Supplier Name (from POE)",
            "First POE Date",
            "POE Count",
            "POE IDs",
            "POE Items Count",
            "POE Total Export Amount (GBP)",
            "Has POE",
            "Export Coverage Ratio",
            "Amount Diff (POE - ANNA Net)",
            "Export Status",
            "Need Review",
        ]
        pd.DataFrame(columns=cols).to_excel(output_path, index=False)
        print(f"[WARN] V3 结果为空（已输出空模板）：{output_path}")
        return output_path

    # 列名整理
    result_df = result_df.rename(columns={
        "order_number": "Order Number",
        "supplier_name": "Supplier Name (from POE)",
        "first_poe_date": "First POE Date",
        "poe_count": "POE Count",
        "poe_ids": "POE IDs",
        "items_count": "POE Items Count",
        "poe_total_export_amount_gbp": "POE Total Export Amount (GBP)",

        "anna_txn_count": "ANNA Txn Count",
        "anna_first_authorised_date": "ANNA First Authorised Date",
        "anna_purchase_amount_gbp": "ANNA Purchase Amount (GBP)",
        "anna_refund_amount_gbp": "ANNA Refund Amount (GBP)",
        "anna_net_amount_gbp": "ANNA Net Amount (GBP)",
        "anna_categories": "ANNA Categories",
        "anna_counterparties": "ANNA Counterparties",
    })

    # 计算判断列
    poe_amt = pd.to_numeric(result_df["POE Total Export Amount (GBP)"], errors="coerce")
    net_amt = pd.to_numeric(result_df["ANNA Net Amount (GBP)"], errors="coerce")

    result_df["Has POE"] = poe_amt.notna()
    denom = net_amt.replace(0, pd.NA)
    result_df["Export Coverage Ratio"] = (poe_amt.fillna(0) / denom).round(4)
    result_df["Amount Diff (POE - ANNA Net)"] = (poe_amt.fillna(0) - net_amt.fillna(0)).round(2)

    def _export_status(has_poe, netv, poev):
        if not has_poe:
            return "未出口/无POE"
        if pd.isna(netv) or netv <= 0:
            return "异常/净额为0"
        ratio = (0 if pd.isna(poev) else float(poev)) / float(netv)
        if ratio >= coverage_full_threshold:
            return "全部出口"
        if 0 < ratio < coverage_full_threshold:
            return "部分出口/可能退货或未出完"
        return "异常"

    result_df["Export Status"] = [
        _export_status(h, n, p)
        for h, n, p in zip(result_df["Has POE"], net_amt, poe_amt)
    ]

    cats = result_df["ANNA Categories"].fillna("").astype(str).str.lower()
    result_df["Need Review"] = (
        (result_df["Has POE"] == True) &
        (result_df["Amount Diff (POE - ANNA Net)"].abs() >= float(diff_threshold_gbp))
    )
    result_df.loc[(result_df["Has POE"] == False) & (cats.str.contains("stock")), "Need Review"] = True

    # 排序：先看需要复核
    result_df = result_df.sort_values(
        by=["Need Review", "ANNA First Authorised Date", "Order Number"],
        ascending=[False, True, True]
    )

    result_df.to_excel(output_path, index=False)
    print(f"[OK] 已生成 V3（ANNA主表）Excel：{output_path}")
    return output_path

def generate_anna_transactions_with_poe_excel(
    start_date: DateLike,
    end_date: DateLike,
    output_path: str,
    conn: Optional[psycopg2.extensions.connection] = None,
) -> str:
    """
    事务级审计视图（ANNA 为主）：
    - 一行 = 一条 ANNA transaction（不丢任何一条）
    - 通过 order_number LEFT JOIN POE 汇总
    - 同一订单多次付款 → 多行显示同一份 POE 信息（完全正常）
    - 输出新增两列：
        1) ANNA Amount - POE Total Amount (GBP)
        2) Stock but No POE (Flag)  (ANNA Category=stock 且 POE IDs 为空)
      两列放在 Supplier Name 之后
    """

    start_date = _normalize_date(start_date)
    end_date = _normalize_date(end_date)

    own_conn = False
    if conn is None:
        conn = psycopg2.connect(**PGSQL_CONFIG)
        own_conn = True

    try:
        # ------------------------------------------------------------------
        # 1) ANNA 主表：逐条交易（不 group、不筛 order_number）
        # ------------------------------------------------------------------
        anna_sql = """
            SELECT
                id AS anna_txn_id,
                authorised_on::date AS authorised_date,
                amount,
                description,
                anna_category,
                counterparty,

                CASE
                    WHEN order_number IS NULL THEN NULL
                    WHEN order_number::text ~ '\\.0$'
                        THEN regexp_replace(order_number::text, '\\.0$', '')
                    ELSE order_number::text
                END AS order_number
            FROM public.anna_transactions
            WHERE authorised_on::date BETWEEN %(start_date)s AND %(end_date)s
            ORDER BY authorised_on
        """
        anna_df = pd.read_sql(
            anna_sql,
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )

        # ------------------------------------------------------------------
        # 2) POE 订单级汇总（按 poe_date 窗口）
        # ------------------------------------------------------------------
        poe_sql = """
            SELECT
                CASE
                    WHEN supplier_order_no ~ '\\.0$'
                        THEN regexp_replace(supplier_order_no, '\\.0$', '')
                    ELSE supplier_order_no
                END AS order_number,

                supplier_name,
                MIN(poe_date)::date AS poe_date,
                COUNT(DISTINCT poe_id) AS poe_count,
                STRING_AGG(DISTINCT poe_id, ', ' ORDER BY poe_id) AS poe_ids,
                SUM(quantity)::int AS items_count,
                ROUND(SUM(purchase_unit_cost_gbp)::numeric, 2) AS poe_total_amount_gbp
            FROM public.export_shipments
            WHERE supplier_order_no IS NOT NULL
              AND poe_date::date BETWEEN %(start_date)s AND %(end_date)s
            GROUP BY 1, supplier_name
        """
        poe_df = pd.read_sql(
            poe_sql,
            conn,
            params={"start_date": start_date, "end_date": end_date},
        )

        # ------------------------------------------------------------------
        # 3) 生成 NOTE（复用 build_anna_note_for_group）
        #     说明：这里仍然按你现在的逻辑逐订单查询（功能优先）
        # ------------------------------------------------------------------
        note_rows = []
        for _, row in poe_df.iterrows():
            order_no = row["order_number"]
            supplier_name = row["supplier_name"]

            poe_items_sql = """
                SELECT
                    poe_id,
                    poe_date,
                    skuid,
                    quantity,
                    purchase_unit_cost_gbp
                FROM public.export_shipments
                WHERE supplier_order_no IS NOT NULL
                  AND (
                      CASE
                          WHEN supplier_order_no ~ '\\.0$'
                              THEN regexp_replace(supplier_order_no, '\\.0$', '')
                          ELSE supplier_order_no
                      END
                  ) = %(order_no)s
            """
            poe_items = pd.read_sql(poe_items_sql, conn, params={"order_no": order_no})

            note = build_anna_note_for_group(
                order_no=order_no,
                supplier_name=supplier_name,
                poe_rows=poe_items,
                total_cost_gbp=float(row["poe_total_amount_gbp"]) if row["poe_total_amount_gbp"] is not None else 0.0,
            )
            note_rows.append({"order_number": order_no, "ANNA NOTE": note})

        note_df = pd.DataFrame(note_rows)

    finally:
        if own_conn:
            conn.close()

    # ----------------------------------------------------------------------
    # 4) JOIN：ANNA 主表 LEFT JOIN POE 汇总 + NOTE
    # ----------------------------------------------------------------------
    result_df = (
        anna_df.merge(poe_df, how="left", on="order_number")
              .merge(note_df, how="left", on="order_number")
    )

    # ----------------------------------------------------------------------
    # 5) 先 rename（让列名一致），再计算新增两列（避免 KeyError）
    # ----------------------------------------------------------------------
    result_df = result_df.rename(columns={
        "authorised_date": "ANNA Date",
        "amount": "ANNA Amount",
        "description": "ANNA Description",
        "anna_category": "ANNA Category",
        "supplier_name": "Supplier Name",
        "poe_date": "POE Date",
        "poe_count": "POE Count",
        "poe_ids": "POE IDs",
        "items_count": "POE Items Count",
        "poe_total_amount_gbp": "POE Total Amount (GBP)",
    })

    # ANNA Amount 为负数（支出），这里用“相加”得到直观差额：(-amount) 与 POE 抵消后的剩余
    result_df["ANNA Amount - POE Total Amount (GBP)"] = (
        pd.to_numeric(result_df["ANNA Amount"], errors="coerce").fillna(0)
        + pd.to_numeric(result_df["POE Total Amount (GBP)"], errors="coerce").fillna(0)
    ).round(2)


    # ===== 新增列2：重点关注（stock 且 POE IDs 为空）=====
    cat_lower = result_df["ANNA Category"].fillna("").astype(str).str.strip().str.lower()
    poe_ids_series = result_df.get("POE IDs")
    poe_ids_empty = poe_ids_series.isna() | (poe_ids_series.astype(str).str.strip() == "")
    result_df["Stock but No POE (Flag)"] = (cat_lower == "stock") & poe_ids_empty

    # ----------------------------------------------------------------------
    # 6) 输出列顺序：两列放在 Supplier Name 后
    # ----------------------------------------------------------------------
    final_columns = [
        "ANNA Date",
        "order_number",
        "ANNA Amount",
        "ANNA Category",
        "ANNA Description",

        "Supplier Name",
        "ANNA Amount - POE Total Amount (GBP)",
        "Stock but No POE (Flag)",

        "POE Date",
        "POE Count",
        "POE IDs",
        "POE Items Count",
        "POE Total Amount (GBP)",
        "ANNA NOTE",
    ]

    # 兜底：避免偶发缺列导致 KeyError（比如某次 NOTE 没生成）
    for c in final_columns:
        if c not in result_df.columns:
            result_df[c] = pd.NA

    result_df = result_df[final_columns]

    # ----------------------------------------------------------------------
    # 7) 写 Excel
    # ----------------------------------------------------------------------
    result_df.to_excel(output_path, index=False)
    print(f"[OK] 已生成 ANNA 事务级 + POE 对账 Excel：{output_path}")
    print(f"[INFO] ANNA rows: {len(anna_df)}, output rows: {len(result_df)}")
    return output_path




# 可选：保留命令行入口（不影响 pipeline import）
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="导出按 Supplier Order No 汇总的 POE/CI 信息，用于 ANNA Note。"
    )
    parser.add_argument("--start-date", required=True, help="开始日期，格式 YYYY-MM-DD，例如 2025-10-01")
    parser.add_argument("--end-date", required=True, help="结束日期，格式 YYYY-MM-DD，例如 2025-10-31")
    parser.add_argument("--output", required=True, help="输出的 Excel 文件路径，例如 D:/supplier_orders_notes.xlsx")

    args = parser.parse_args()
    generate_supplier_orders_excel(args.start_date, args.end_date, args.output)
