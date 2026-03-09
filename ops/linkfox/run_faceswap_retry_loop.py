"""
LinkFox 换模特自动循环脚本。

流程（每轮）：
  1. run_linkfox_faceswap.py          — 批量换模特
  2. run_compare_faceswap_quality.py  — 剔除衣服被改的图（共享自 ai_image）
  3. run_find_unprocessed_faceswap.py — 统计仍未完成的编码（共享自 ai_image）

循环条件：codes.xlsx 中仍有编码时继续，全部处理完则退出。

路径配置来自 ops/linkfox/_session_config.py。
"""
import os
import sys
import subprocess
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from _session_config import CODES_EXCEL

import openpyxl

# ============================================================
# 调度参数
# ============================================================
CODES_FILE  = CODES_EXCEL
HEADER_ROWS = 1
MAX_ROUNDS  = 100
# ============================================================


def read_codes_from_excel(path: Path, header_rows: int = 1) -> list[str]:
    if not path.is_file():
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    codes: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < header_rows:
            continue
        val = row[0] if row else None
        if val is not None and str(val).strip():
            codes.append(str(val).strip())
    wb.close()
    return codes


def run_script(script_path: Path) -> None:
    cmd = [sys.executable, str(script_path)]
    print(f"\n{'=' * 80}")
    print(f"执行脚本: {script_path}")
    subprocess.run(cmd, check=True)


def main() -> None:
    scripts = [
        Path(_HERE) / "run_linkfox_faceswap.py",          # 1) 换模特（LinkFox）
        Path(_HERE) / "run_compare_faceswap_quality.py",  # 2) 剔除质量差的图
        Path(_HERE) / "run_find_unprocessed_faceswap.py", # 3) 统计未完成编码
    ]

    for script in scripts:
        if not script.is_file():
            raise FileNotFoundError(f"脚本不存在: {script}")

    for round_no in range(1, MAX_ROUNDS + 1):
        pending_codes = read_codes_from_excel(CODES_FILE, HEADER_ROWS)
        print(f"\n{'#' * 80}")
        print(f"第 {round_no} 轮开始，待处理编码数: {len(pending_codes)}")

        if not pending_codes:
            print("codes.xlsx 中已无待处理编码，循环结束。")
            return

        print(f"待处理编码: {pending_codes}")

        for script in scripts:
            run_script(script)

        remaining_codes = read_codes_from_excel(CODES_FILE, HEADER_ROWS)
        print(f"\n第 {round_no} 轮结束，剩余编码数: {len(remaining_codes)}")
        if not remaining_codes:
            print("所有编码都已换模特成功，循环结束。")
            return

    raise RuntimeError(
        f"循环已达到 MAX_ROUNDS={MAX_ROUNDS}，但 {CODES_FILE} 中仍有未处理编码，请检查失败原因。"
    )


if __name__ == "__main__":
    main()
