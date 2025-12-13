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
