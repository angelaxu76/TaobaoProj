# -*- coding: utf-8 -*-
"""
将从 HMRC / ASM 下载的 POE 文件自动分类到 POE_References 目录下的日期子目录。

支持两类文件：
  Excel： GB-EMINZORA-YYMMDD-N.xlsx  → 从文件名解析日期
  PDF：   poe_SD*.pdf                 → 读取 PDF 内容提取 Lodged 日期

目标结构：
  POE_References/
    ├── 20251121/
    │     ├── GB-EMINZORA-251121-1.xlsx
    │     └── poe_SD10010097776771.pdf
    ├── 20251127/
    │     ├── GB-EMINZORA-251127-1.xlsx
    │     └── poe_SD10010129248974.pdf
    ...

用法：
  1. 修改下方 CONFIG 区域中的路径（或保持默认）。
  2. 先以 DRY_RUN = True 预览，确认无误后改为 False 正式执行。
  3. python finance/pipeline/run_sort_poe_downloads.py

依赖：pip install PyPDF2
"""

from __future__ import annotations
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============================================================
# CONFIG（按需修改）
# ============================================================
INPUT_DIR  = r"C:\Users\angel\Downloads"
OUTPUT_DIR = r"C:\Users\angel\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_References"

# True = 仅预览，不实际移动文件；False = 正式执行
DRY_RUN = False

# True = 移动（从 Downloads 删除）；False = 复制（保留 Downloads 原文件）
MOVE_FILES = False
# ============================================================


# ── Excel：从文件名提取日期 ────────────────────────────────────────────────────
# GB-EMINZORA-251121-1.xlsx → YYMMDD=251121 → 20251121
_EXCEL_PATTERN = re.compile(
    r"^GB-EMINZORA-(\d{2})(\d{2})(\d{2})-\d+\.xlsx$",
    re.IGNORECASE,
)


def _date_from_excel_name(filename: str) -> Optional[str]:
    """返回 'YYYYMMDD' 或 None。"""
    m = _EXCEL_PATTERN.match(filename)
    if not m:
        return None
    yy, mm, dd = m.group(1), m.group(2), m.group(3)
    year = f"20{yy}"
    try:
        datetime.strptime(f"{year}{mm}{dd}", "%Y%m%d")
    except ValueError:
        return None
    return f"{year}{mm}{dd}"


# ── PDF：读取内容提取 Lodged 日期 ──────────────────────────────────────────────
# 文本中含 "Lodged\n21/11/2025 15:46" 或 "Lodged 21/11/2025"
_LODGED_PATTERN = re.compile(
    r"Lodged\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
# 备用：Status date/time 后跟日期
_STATUS_PATTERN = re.compile(
    r"Status\s+date/time\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
# 备用：ASM ADMIN DD/MM/YYYY
_ASM_PATTERN = re.compile(
    r"ASM\s+ADMIN\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def _read_pdf_text(path: str) -> str:
    try:
        import PyPDF2  # type: ignore
    except ImportError:
        raise RuntimeError("缺少依赖：pip install PyPDF2")
    chunks = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                pass
    return "\n".join(chunks)


def _date_from_pdf(path: str) -> Optional[str]:
    """读取 POE PDF，返回 'YYYYMMDD' 或 None。"""
    try:
        text = _read_pdf_text(path)
    except Exception as e:
        print(f"    [警告] 读取 PDF 失败 ({Path(path).name}): {e}")
        return None

    for pat in (_LODGED_PATTERN, _STATUS_PATTERN, _ASM_PATTERN):
        m = pat.search(text)
        if m:
            raw = m.group(1)  # DD/MM/YYYY
            try:
                dt = datetime.strptime(raw, "%d/%m/%Y")
                return dt.strftime("%Y%m%d")
            except ValueError:
                continue
    return None


# ── 主逻辑 ─────────────────────────────────────────────────────────────────────

def _is_poe_excel(name: str) -> bool:
    return bool(_EXCEL_PATTERN.match(name))


def _is_poe_pdf(name: str) -> bool:
    return name.lower().startswith("poe_") and name.lower().endswith(".pdf")


def sort_poe_downloads(
    input_dir: str,
    output_dir: str,
    dry_run: bool = True,
    move: bool = False,
) -> None:
    input_path  = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.is_dir():
        raise FileNotFoundError(f"INPUT_DIR 不存在: {input_path}")

    files = [f for f in input_path.iterdir() if f.is_file()]
    excel_files = [f for f in files if _is_poe_excel(f.name)]
    pdf_files   = [f for f in files if _is_poe_pdf(f.name)]
    total = len(excel_files) + len(pdf_files)

    print(f"{'=' * 60}")
    print(f"扫描目录：{input_path}")
    print(f"找到 Excel: {len(excel_files)} 个 | PDF: {len(pdf_files)} 个")
    print(f"目标根目录：{output_path}")
    print(f"模式：{'DRY RUN（仅预览）' if dry_run else ('移动' if move else '复制')}")
    print(f"{'=' * 60}\n")

    ok = skip = fail = 0
    action = "移动" if move else "复制"

    def _process(src: Path, date_str: Optional[str]) -> None:
        nonlocal ok, skip, fail
        if not date_str:
            print(f"  [跳过] {src.name} — 无法解析日期")
            fail += 1
            return

        target_dir  = output_path / date_str
        target_file = target_dir / src.name

        if target_file.exists():
            print(f"  [已存在] {src.name} → {target_dir.name}/  (跳过)")
            skip += 1
            return

        print(f"  [{action}] {src.name}  →  {target_dir.name}/")
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(src), str(target_file))
            else:
                shutil.copy2(str(src), str(target_file))
        ok += 1

    # 处理 Excel
    print("── Excel 文件 ──")
    for f in sorted(excel_files):
        _process(f, _date_from_excel_name(f.name))

    # 处理 PDF
    print("\n── PDF 文件 ──")
    for f in sorted(pdf_files):
        print(f"  [读取] {f.name} ...")
        date_str = _date_from_pdf(str(f))
        _process(f, date_str)

    print(f"\n{'=' * 60}")
    print(f"{'[DRY RUN] ' if dry_run else ''}完成：{action} {ok} 个 | 已跳过 {skip} 个 | 失败 {fail} 个 | 共 {total} 个")
    if dry_run:
        print("→ 确认无误后将 DRY_RUN 改为 False 再次运行。")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    sort_poe_downloads(INPUT_DIR, OUTPUT_DIR, dry_run=DRY_RUN, move=MOVE_FILES)
