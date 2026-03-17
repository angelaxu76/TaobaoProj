"""
批量导出 POE 成本填写模板 Excel。

按日期范围自动扫描 POE_References 目录，提取各日期子目录中的 POE ID，
为每个 POE 生成一份待填写的 {poe_id}_costs.xlsx 模板。

已存在的模板文件会自动跳过（不覆盖已填写的数据）。

用法：修改下方 CONFIG 区域后运行：
    python finance/pipeline/run_poe_order_export_excel.py
"""
import re
import sys
from pathlib import Path

from finance.ingest.manage_export_shipments_costs import export_poe_cost_template

# ============================================================
# CONFIG（按需修改）
# ============================================================

# 扫描 POE_References 的根目录
POE_REFERENCES_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References"

# 日期范围（含两端），格式 YYYYMMDD；None 表示不限
DATE_FROM = "20251201"
DATE_TO   = "20260304"

# 模板输出目录
OUTPUT_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES"

# ============================================================

_POE_PDF_RE = re.compile(r"poe_(SD\d+)\.pdf", re.IGNORECASE)
_DIR_DATE_RE = re.compile(r"^\d{8}$")


def _collect_poe_ids(references_dir: str, date_from: str | None, date_to: str | None) -> list[tuple[str, str]]:
    """
    扫描 references_dir 下所有形如 YYYYMMDD 的子目录，
    在日期范围内时提取其中 poe_SD*.pdf 的 POE ID。

    返回 [(poe_id, date_str), ...] 按日期排序。
    """
    root = Path(references_dir)
    results: list[tuple[str, str]] = []

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

        for f in subdir.iterdir():
            m = _POE_PDF_RE.match(f.name)
            if m:
                results.append((m.group(1), date_str))
                break  # 每个目录只取第一个 poe pdf

    return results


def main():
    entries = _collect_poe_ids(POE_REFERENCES_DIR, DATE_FROM, DATE_TO)

    if not entries:
        print(f"日期范围 {DATE_FROM} ~ {DATE_TO} 内未找到任何 POE 目录，请检查路径和日期。")
        return

    print(f"日期范围：{DATE_FROM} ~ {DATE_TO}  共找到 {len(entries)} 个 POE\n")

    ok = skipped = failed = 0
    output_root = Path(OUTPUT_DIR)

    for poe_id, date_str in entries:
        output_path = output_root / f"{poe_id}_costs.xlsx"
        print(f"  [{date_str}] {poe_id} → {output_path.name}", end="  ")
        try:
            result = export_poe_cost_template(poe_id, str(output_path))
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
