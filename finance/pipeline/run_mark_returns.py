"""
批量将退货订单标记到 export_shipments 表。

输入 Excel 两列（无需表头以外的任何字段）：
    shipment_id    return_date
    SD10010097xxx  2026-01-15
    SD10010129xxx  2026-01-20
    ...

return_date 留空时统一使用今天的日期。

用法：
    1. 修改下方 INPUT_EXCEL 路径。
    2. 先以 DRY_RUN = True 预览受影响行，确认后改为 False 正式写库。
    3. python finance/pipeline/run_mark_returns.py
"""

from __future__ import annotations
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import PGSQL_CONFIG

# ============================================================
# CONFIG
# ============================================================
INPUT_EXCEL = r"C:\Users\angel\Downloads\returns.xlsx"
DRY_RUN     = True
# ============================================================

COL_SHIPMENT_ID = 0   # 第 A 列
COL_RETURN_DATE = 1   # 第 B 列
HEADER_ROWS     = 1


def _read_input(path: str) -> list[tuple[str, date]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    today = date.today()
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < HEADER_ROWS:
            continue
        sid = row[COL_SHIPMENT_ID]
        if not sid or not str(sid).strip():
            continue
        sid = str(sid).strip()

        raw_date = row[COL_RETURN_DATE] if len(row) > COL_RETURN_DATE else None
        if isinstance(raw_date, (datetime, date)):
            ret_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        elif raw_date and str(raw_date).strip():
            try:
                ret_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
            except ValueError:
                try:
                    ret_date = datetime.strptime(str(raw_date).strip(), "%d/%m/%Y").date()
                except ValueError:
                    print(f"  [警告] 日期格式无法解析 ({sid}): {raw_date}，使用今天")
                    ret_date = today
        else:
            ret_date = today

        rows.append((sid, ret_date))
    wb.close()
    return rows


def main():
    entries = _read_input(INPUT_EXCEL)
    if not entries:
        print("未读取到任何记录，请检查 INPUT_EXCEL 路径和格式。")
        return

    print(f"读取到 {len(entries)} 条退货记录")
    print(f"模式：{'DRY RUN（仅预览）' if DRY_RUN else '正式写库'}\n")

    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur  = conn.cursor()

    ok = notfound = already = 0

    for shipment_id, ret_date in entries:
        # 查当前状态
        cur.execute(
            "SELECT id, is_returned FROM public.export_shipments WHERE shipment_id = %s",
            (shipment_id,)
        )
        rows = cur.fetchall()

        if not rows:
            print(f"  [未找到] {shipment_id}")
            notfound += 1
            continue

        if all(r[1] for r in rows):   # 所有行已是 returned
            print(f"  [已标记] {shipment_id}（跳过）")
            already += 1
            continue

        affected = len(rows)
        print(f"  [标记]   {shipment_id}  return_date={ret_date}  ({affected} 行)")

        if not DRY_RUN:
            cur.execute(
                """UPDATE public.export_shipments
                      SET is_returned = TRUE,
                          return_date = %s,
                          updated_at  = NOW()
                    WHERE shipment_id = %s
                      AND (is_returned IS FALSE OR is_returned IS NULL)""",
                (ret_date, shipment_id)
            )
        ok += 1

    if not DRY_RUN:
        conn.commit()

    cur.close()
    conn.close()

    print(f"\n{'=' * 50}")
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}完成：标记 {ok} 条 | 已存在 {already} 条 | 未找到 {notfound} 条")
    if DRY_RUN:
        print("→ 确认无误后将 DRY_RUN 改为 False 再次运行。")


if __name__ == "__main__":
    main()
