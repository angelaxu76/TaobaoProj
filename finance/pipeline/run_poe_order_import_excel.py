"""
Step 4：将填好的成本 Excel 导入数据库，并在导入后自动检查缺口。

- 扫描 BASE_DIR 下所有 *_costs.xlsx（跳过 ~ 临时文件）
- 匹配键：(shipment_id, skuid)，与文件命名无关
- 导入完成后自动查询仍有缺口的批次，生成 {BASE_DIR}/TOPUP_{date}.xlsx
  供下一轮补填；若无缺口则不生成文件

用法：按需修改 BASE_DIR 后直接运行
    python finance/pipeline/run_poe_order_import_excel.py
"""
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import psycopg2
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import PGSQL_CONFIG
from finance.ingest.manage_export_shipments_costs import import_poe_cost_from_excel

# ============================================================
# CONFIG
# ============================================================
BASE_DIR = Path(r"G:\temp\taobao\poe")
# ============================================================


def _check_and_generate_topup(base_dir: Path) -> None:
    """
    导入后检查所有批次的缺口，若存在则生成一份合并补丁文件。
    空 SKU / 空 shipment_id 的汇总行自动忽略。
    """
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT folder_name, poe_id, shipment_id, skuid, value_gbp, id
        FROM export_shipments
        WHERE purchase_unit_cost_gbp IS NULL
          AND shipment_id IS NOT NULL AND shipment_id != ''
          AND skuid       IS NOT NULL AND skuid       != ''
        ORDER BY folder_name, shipment_id, skuid
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("\n[OK] 所有批次成本已完整，无需补填。")
        return

    df = pd.DataFrame(rows, columns=["folder_name","poe_id","shipment_id","skuid","value_gbp","id"])
    df["supplier_name"]          = ""
    df["supplier_order_no"]      = ""
    df["purchase_unit_cost_gbp"] = ""

    col_order = ["folder_name","poe_id","shipment_id","skuid","value_gbp",
                 "supplier_name","supplier_order_no","purchase_unit_cost_gbp","id"]

    topup_path = base_dir / f"TOPUP_{date.today().strftime('%Y%m%d')}.xlsx"
    with pd.ExcelWriter(topup_path, engine="xlsxwriter") as w:
        df[col_order].to_excel(w, sheet_name="MISSING_COSTS", index=False)
        ws = w.sheets["MISSING_COSTS"]
        for col, width in enumerate([12, 22, 18, 22, 10, 16, 24, 22, 8]):
            ws.set_column(col, col, width)

    # 按批次汇总打印
    summary = df.groupby(["folder_name","poe_id"]).size().reset_index(name="missing")
    print(f"\n[警告] 以下批次仍有 {len(df)} 条记录缺少成本：")
    for _, r in summary.iterrows():
        print(f"  {r['folder_name']}  {r['poe_id']}  缺 {r['missing']} 条")
    print(f"\n[INFO] 补填模板已生成：{topup_path.name}")
    print("       填好后再次运行本脚本即可。")


def main():
    excel_files = sorted(
        f for f in BASE_DIR.glob("*_costs.xlsx")
        if not f.name.startswith("~") and "TOPUP" not in f.name
    )

    if not excel_files:
        print(f"[WARN] 未找到 *_costs.xlsx：{BASE_DIR}")
    else:
        print(f"找到 {len(excel_files)} 个模板文件\n")
        total_updated = 0
        for f in excel_files:
            print(f"  导入 {f.name} ...", end="  ")
            try:
                n = import_poe_cost_from_excel(str(f))
                print(f"更新 {n} 行")
                total_updated += n
            except Exception as e:
                print(f"[ERROR] {e}")
        print(f"\n合计更新 {total_updated} 行")

    # 无论是否有文件，都执行缺口检查
    _check_and_generate_topup(BASE_DIR)


if __name__ == "__main__":
    main()
