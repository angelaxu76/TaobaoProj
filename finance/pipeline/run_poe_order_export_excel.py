"""
批量导出 POE 成本填写模板 Excel。

按日期范围自动扫描 POE_References 目录，为每个日期批次
生成一份待填写的 {date}_costs.xlsx 模板。

主键改用日期目录名（folder_name），不再依赖 poe_id，
适用于 POE PDF 缺失或 poe_id 未正确入库的批次。

已存在的模板文件会自动跳过（不覆盖已填写的数据）。

用法：修改下方 CONFIG 区域后运行：
    python finance/pipeline/run_poe_order_export_excel.py
"""
import re
from pathlib import Path

from finance.ingest.manage_export_shipments_costs import export_cost_template_by_folder

# ============================================================
# CONFIG（按需修改）
# ============================================================

# 扫描 POE_References 的根目录
POE_REFERENCES_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References"

# 日期范围（含两端），格式 YYYYMMDD；None 表示不限
DATE_FROM = "20251001"
DATE_TO   = "20260410"

# 模板输出目录
OUTPUT_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES"

# ============================================================

_DIR_DATE_RE = re.compile(r"^\d{8}$")


def _collect_date_folders(references_dir: str, date_from: str | None, date_to: str | None) -> list[str]:
    """
    扫描 references_dir 下所有形如 YYYYMMDD 的子目录，
    返回在日期范围内的目录名列表（按日期排序）。
    """
    root = Path(references_dir)
    results: list[str] = []

    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        date_str = subdir.name
        if not _DIR_DATE_RE.match(date_str):
            continue
        if date_from and date_str < date_from:
            continue
        if date_to and date_str > date_to:
            continue
        results.append(date_str)

    return results


def main():
    folders = _collect_date_folders(POE_REFERENCES_DIR, DATE_FROM, DATE_TO)

    if not folders:
        print(f"日期范围 {DATE_FROM} ~ {DATE_TO} 内未找到任何日期目录，请检查路径和日期。")
        return

    print(f"日期范围：{DATE_FROM} ~ {DATE_TO}  共找到 {len(folders)} 个批次\n")

    ok = skipped = failed = 0
    output_root = Path(OUTPUT_DIR)

    for date_str in folders:
        output_path = output_root / f"{date_str}_costs.xlsx"
        print(f"  [{date_str}] → {output_path.name}", end="  ")
        try:
            result = export_cost_template_by_folder(date_str, str(output_path))
            if "跳过" in (result or ""):
                skipped += 1
            else:
                print("✓")
                ok += 1
        except ValueError as e:
            print(f"✗  {e}")
            failed += 1
        except Exception as e:
            print(f"✗  意外错误: {e}")
            failed += 1

    print(f"\n完成：生成 {ok} 个 | 跳过（已存在）{skipped} 个 | 失败 {failed} 个")


if __name__ == "__main__":
    main()
