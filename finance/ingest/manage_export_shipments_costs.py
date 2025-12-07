import os
import sys
from pathlib import Path

import psycopg2
import pandas as pd

from config import PGSQL_CONFIG  # 按你项目实际位置调整


def get_conn():
    """
    获取 Postgres 连接。
    依赖 config.PGSQL_CONFIG，结构类似：
    {
        "host": "...",
        "port": 5432,
        "dbname": "...",
        "user": "...",
        "password": "...",
    }
    """
    return psycopg2.connect(**PGSQL_CONFIG)


def export_poe_cost_template(poe_id: str, output_excel_path: str) -> str:
    """
    按给定 poe_id，从 export_shipments 导出 Excel 模板：

    列顺序：
      1) shipment_id
      2) skuid
      3) value_gbp
      4) supplier_name            （空）
      5) supplier_order_no        （空）
      6) purchase_unit_cost_gbp   （空）
      7) id（隐藏用：用于回写时定位记录）

    返回：输出 Excel 的绝对路径
    """
    output_path = Path(output_excel_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sql = """
        SELECT
            id,
            shipment_id,
            skuid,
            value_gbp
        FROM public.export_shipments
        WHERE poe_id = %s
        ORDER BY shipment_id NULLS LAST, skuid NULLS LAST, id;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (poe_id,))
            rows = cur.fetchall()

    if not rows:
        raise ValueError(f"没有找到 poe_id = {poe_id} 的记录。")

    # 构造 DataFrame —— 列名要和 SELECT 的顺序一致
    df = pd.DataFrame(rows, columns=["id", "shipment_id", "skuid", "value_gbp"])

    # 按你要求的列顺序输出到 Excel
    df_export = pd.DataFrame()
    df_export["shipment_id"] = df["shipment_id"]
    df_export["skuid"] = df["skuid"]
    df_export["value_gbp"] = df["value_gbp"]

    # 三个空白栏供手工填写
    df_export["supplier_name"] = ""
    df_export["supplier_order_no"] = ""
    df_export["purchase_unit_cost_gbp"] = ""

    # id 用于回写数据库
    df_export["id"] = df["id"]

    # 写 Excel
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="POE_COST_TEMPLATE", index=False)

    return str(output_path.resolve())



def import_poe_cost_from_excel(excel_path: str) -> int:
    """
    将你手工填好的 Excel 导回 export_shipments：

    要求 Excel 至少包含列：
      - id
      - supplier_name
      - supplier_order_no
      - purchase_unit_cost_gbp

    逻辑：
      - 只更新那些任意一个供应商字段非空的行
      - 对应记录通过 id 精确匹配

    返回：成功更新的行数
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")

    df = pd.read_excel(path, sheet_name=0)

    required_cols = {"id", "supplier_name", "supplier_order_no", "purchase_unit_cost_gbp"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少必需列: {', '.join(missing)}")

    # 只保留有任意非空填写的行
    mask = (
        df["supplier_name"].astype(str).str.strip().ne("") |
        df["supplier_order_no"].astype(str).str.strip().ne("") |
        df["purchase_unit_cost_gbp"].notna()
    )
    df_update = df[mask].copy()

    if df_update.empty:
        print("Excel 中没有任何供应商字段被填写，不进行更新。")
        return 0

    # 转换 purchase_unit_cost_gbp 为 float（如果是空字符串则变为 None）
    def _to_float_or_none(x):
        if pd.isna(x):
            return None
        if isinstance(x, str) and not x.strip():
            return None
        try:
            return float(x)
        except ValueError:
            return None

    df_update["purchase_unit_cost_gbp"] = df_update["purchase_unit_cost_gbp"].apply(_to_float_or_none)

    sql = """
        UPDATE public.export_shipments
        SET supplier_name = %s,
            supplier_order_no = %s,
            purchase_unit_cost_gbp = %s
        WHERE id = %s
    """

    updated = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for _, row in df_update.iterrows():
                row_id = int(row["id"])
                supplier_name = (str(row["supplier_name"]).strip()
                                 if not pd.isna(row["supplier_name"]) else None)
                supplier_order_no = (str(row["supplier_order_no"]).strip()
                                     if not pd.isna(row["supplier_order_no"]) else None)
                purchase_cost = row["purchase_unit_cost_gbp"]

                cur.execute(
                    sql,
                    (supplier_name or None,
                     supplier_order_no or None,
                     purchase_cost,
                     row_id),
                )
                updated += 1

    return updated


def main():
    """
    命令行用法示例：

    1）导出模板：
       python manage_export_shipments_costs.py export <poe_id> <output_excel_path>

       例如：
       python manage_export_shipments_costs.py export SD10XXXXX D:\Temp\poe_SD10XXXXX_costs.xlsx

    2）导入已填写的模板：
       python manage_export_shipments_costs.py import <excel_path>

       例如：
       python manage_export_shipments_costs.py import D:\Temp\poe_SD10XXXXX_costs.xlsx
    """
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Export template: python manage_export_shipments_costs.py export <poe_id> <output_excel_path>")
        print("  Import filled:   python manage_export_shipments_costs.py import <excel_path>")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "export":
        if len(sys.argv) < 4:
            print("Usage: python manage_export_shipments_costs.py export <poe_id> <output_excel_path>")
            sys.exit(1)
        poe_id = sys.argv[2]
        output_path = sys.argv[3]
        result_path = export_poe_cost_template(poe_id, output_path)
        print(f"[OK] Exported template for poe_id={poe_id} -> {result_path}")

    elif mode == "import":
        excel_path = sys.argv[2]
        updated = import_poe_cost_from_excel(excel_path)
        print(f"[OK] Updated {updated} rows from {excel_path}")

    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
