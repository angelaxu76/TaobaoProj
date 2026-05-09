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

    # 已存在则跳过，防止覆盖已填写的成本数据
    if output_path.exists():
        print(f"[跳过] 文件已存在，不覆盖: {output_path.name}")
        return str(output_path.resolve())

    sql = """
        SELECT
            id,
            shipment_id,
            skuid,
            value_gbp
        FROM public.export_shipments
        WHERE poe_id = %s
          AND shipment_id IS NOT NULL AND shipment_id != ''
          AND skuid       IS NOT NULL AND skuid       != ''
        ORDER BY shipment_id NULLS LAST, skuid NULLS LAST, id;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (poe_id,))
            rows = cur.fetchall()

    if not rows:
        raise ValueError(f"没有找到 poe_id = {poe_id} 的记录。")

    df = pd.DataFrame(rows, columns=["id", "shipment_id", "skuid", "value_gbp"])

    df_export = pd.DataFrame()
    df_export["shipment_id"] = df["shipment_id"]
    df_export["skuid"] = df["skuid"]
    df_export["value_gbp"] = df["value_gbp"]
    df_export["supplier_name"] = ""
    df_export["supplier_order_no"] = ""
    df_export["purchase_unit_cost_gbp"] = ""
    df_export["id"] = df["id"]

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="POE_COST_TEMPLATE", index=False)

    return str(output_path.resolve())


def export_cost_template_by_folder(folder_name: str, output_excel_path: str) -> str:
    """
    按日期目录名（folder_name，如 "20251127"）从 export_shipments 导出成本填写模板。

    不依赖 poe_id，适用于 POE PDF 缺失或 poe_id 未正确入库的批次。
    输出列：
      poe_id（参考用，可能为空）/ shipment_id / skuid / value_gbp /
      supplier_name（空）/ supplier_order_no（空）/ purchase_unit_cost_gbp（空）/ id
    """
    output_path = Path(output_excel_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        print(f"[跳过] 文件已存在，不覆盖: {output_path.name}")
        return "跳过"

    sql = """
        SELECT
            id,
            poe_id,
            shipment_id,
            skuid,
            value_gbp
        FROM public.export_shipments
        WHERE folder_name = %s
          AND shipment_id IS NOT NULL AND shipment_id != ''
          AND skuid       IS NOT NULL AND skuid       != ''
        ORDER BY shipment_id NULLS LAST, skuid NULLS LAST, id;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (folder_name,))
            rows = cur.fetchall()

    if not rows:
        raise ValueError(f"没有找到 folder_name = {folder_name} 的记录。")

    df = pd.DataFrame(rows, columns=["id", "poe_id", "shipment_id", "skuid", "value_gbp"])

    df_export = pd.DataFrame()
    df_export["poe_id"] = df["poe_id"].fillna("")
    df_export["shipment_id"] = df["shipment_id"]
    df_export["skuid"] = df["skuid"]
    df_export["value_gbp"] = df["value_gbp"]
    df_export["supplier_name"] = ""
    df_export["supplier_order_no"] = ""
    df_export["purchase_unit_cost_gbp"] = ""
    df_export["id"] = df["id"]

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="POE_COST_TEMPLATE", index=False)

    return str(output_path.resolve())



def import_poe_cost_from_excel(excel_path: str) -> int:
    """
    将手工填好的 Excel 导回 export_shipments。

    匹配键：(shipment_id, skuid) —— 业务唯一标识，与文件命名无关。
    id 列若存在仅作参考，不用于匹配。

    必需列：shipment_id / skuid / purchase_unit_cost_gbp
    可选列：supplier_name / supplier_order_no

    只更新 purchase_unit_cost_gbp 非空的行；已有值的行也会被覆盖（以 Excel 为准）。
    返回：成功更新的行数。
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")

    df = pd.read_excel(path, sheet_name=0, dtype=str)

    required_cols = {"shipment_id", "skuid", "purchase_unit_cost_gbp"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少必需列: {', '.join(missing)}")

    def _to_float_or_none(x):
        if pd.isna(x) or str(x).strip() in ("", "nan"):
            return None
        try:
            return float(x)
        except ValueError:
            return None

    def _norm_shipment_id(x):
        """将可能是浮点字符串（如 '7.894e+13'）的 shipment_id 规范为纯整数字符串。"""
        x = str(x).strip()
        try:
            return str(int(float(x)))
        except (ValueError, OverflowError):
            return x

    df["purchase_unit_cost_gbp"] = df["purchase_unit_cost_gbp"].apply(_to_float_or_none)
    df_update = df[df["purchase_unit_cost_gbp"].notna()].copy()

    if df_update.empty:
        print("Excel 中 purchase_unit_cost_gbp 均为空，不进行更新。")
        return 0

    sql = """
        UPDATE public.export_shipments
        SET supplier_name          = COALESCE(%s, supplier_name),
            supplier_order_no      = COALESCE(%s, supplier_order_no),
            purchase_unit_cost_gbp = %s
        WHERE shipment_id = %s
          AND skuid       = %s
    """

    updated = not_found = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for _, row in df_update.iterrows():
                sid  = _norm_shipment_id(row["shipment_id"])
                skuid = str(row.get("skuid", "") or "").strip()
                cost  = row["purchase_unit_cost_gbp"]
                sname = str(row.get("supplier_name", "") or "").strip() or None
                sno   = str(row.get("supplier_order_no", "") or "").strip() or None

                cur.execute(sql, (sname, sno, cost, sid, skuid))
                if cur.rowcount:
                    updated += 1
                else:
                    not_found += 1

    if not_found:
        print(f"  [警告] {not_found} 行在数据库中未匹配（shipment_id+skuid 不存在）")
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
