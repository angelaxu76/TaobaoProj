# -*- coding: utf-8 -*-
"""
finance.supplier.rename_parcelbroker_receipts
----------------------------------------------
ParcelBroker 专用：批量读取 PDF 收据，提取订单号、订单日期、含 VAT 总额，
按统一规则重命名后复制到输出目录，同时生成 rename_log.csv。

ParcelBroker 收据字段布局（示例）：
    ORDER DATE    05/Feb/2026
    ORDER NUMBER  MPS156647
    ...
    Total:  £10.45

输出文件名格式（日期在前，便于按时间排序）：
    2026-02-05_ParcelBroker_Receipt_ORDER_MPS156647_£10.45.pdf

依赖：
    pip install PyPDF2

核心函数：
    rename_parcelbroker_receipts(input_dir, output_dir) -> Tuple[int, int, str]
"""

from __future__ import annotations
import os
import re
import shutil
import csv
from typing import Optional, Tuple
from datetime import datetime

BRAND          = "ParcelBroker"
DOC_TYPE       = "Receipt"
CURRENCY_SYMBOL = "£"
LOG_FILENAME   = "rename_log.csv"

# ── Regex patterns ────────────────────────────────────────────────────────────

# 订单号：ORDER NUMBER  MPS156647
ORDER_PATTERN = re.compile(
    r"ORDER\s+NUMBER\s+([A-Z]{2,4}\d{4,})",
    re.IGNORECASE,
)

# 订单日期：ORDER DATE  05/Feb/2026
# 格式：DD/Mon/YYYY（Jan/Feb/Mar ...）
ORDER_DATE_PATTERN = re.compile(
    r"ORDER\s+DATE\s+(\d{1,2}/[A-Za-z]{3}/\d{4})",
    re.IGNORECASE,
)
# 兜底：Collection Date  05 Feb 2026
COLLECTION_DATE_PATTERN = re.compile(
    r"Collection\s+Date\s+(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})",
    re.IGNORECASE,
)

# 总价：Total:  £10.45
TOTAL_PATTERN = re.compile(
    r"\bTotal[:\s]+£\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _need_pypdf2():
    try:
        import PyPDF2  # type: ignore
        return PyPDF2
    except Exception:
        raise RuntimeError("Missing dependency PyPDF2. Please install with: pip install PyPDF2")


def _read_pdf_text(path: str) -> str:
    PyPDF2 = _need_pypdf2()
    chunks = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            chunks.append(t)
    return "\n".join(chunks)


def _parse_date_to_iso(date_str: str) -> Optional[str]:
    """
    支持格式：
      - 05/Feb/2026  → %d/%b/%Y
      - 05 Feb 2026  → %d %b %Y
      - 05 February 2026 → %d %B %Y
      - 05/02/2026   → %d/%m/%Y
    """
    date_str = date_str.strip()
    for fmt in ("%d/%b/%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def _normalize_amount(amount_str: str) -> str:
    amt = amount_str.replace(",", "").strip()
    if re.match(r"^\d+(\.\d{2})?$", amt):
        return amt if "." in amt else f"{amt}.00"
    m = re.search(r"(\d+(?:\.\d{2}))", amt)
    return m.group(1) if m else amt


def _extract_fields(
    text: str,
) -> Tuple[
    Optional[str],  # order_number
    Optional[str],  # date_iso
    Optional[str],  # gbp_amount
]:
    # 订单号
    order = None
    m = ORDER_PATTERN.search(text)
    if m:
        order = m.group(1).upper()

    # 日期（优先 ORDER DATE，备用 Collection Date）
    date_iso = None
    m = ORDER_DATE_PATTERN.search(text)
    if m:
        date_iso = _parse_date_to_iso(m.group(1))
    if not date_iso:
        m = COLLECTION_DATE_PATTERN.search(text)
        if m:
            date_iso = _parse_date_to_iso(m.group(1))

    # 总价（含 VAT）
    gbp_amount = None
    t = re.sub(r"\s+", " ", text).strip()
    m = TOTAL_PATTERN.search(t)
    if m:
        gbp_amount = _normalize_amount(m.group(1))

    return order, date_iso, gbp_amount


def _build_filename(
    order: Optional[str],
    amount: Optional[str],
    date_iso: Optional[str],
) -> Optional[str]:
    """
    日期在最前，便于按时间排序：
    2026-02-05_ParcelBroker_Receipt_ORDER_MPS156647_£10.45.pdf
    """
    if not order:
        return None
    parts = []
    if date_iso:
        parts.append(date_iso)
    parts.extend([BRAND, DOC_TYPE, f"ORDER_{order}"])
    if amount:
        parts.append(f"{CURRENCY_SYMBOL}{amount}")
    return "_".join(parts) + ".pdf"


# ── 主入口 ────────────────────────────────────────────────────────────────────

def rename_parcelbroker_receipts(input_dir: str, output_dir: str) -> Tuple[int, int, str]:
    """
    读取 input_dir 下所有 PDF，重命名后复制到 output_dir。
    返回: (total, renamed, log_path)
    """
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    os.makedirs(output_dir, exist_ok=True)

    pdfs = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
    log_path = os.path.join(output_dir, LOG_FILENAME)
    total = len(pdfs)
    renamed = 0

    with open(log_path, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        w.writerow([
            "old_name", "new_name",
            "order_number", "date_iso", "amount_gbp", "status",
        ])

        for fname in pdfs:
            src = os.path.join(input_dir, fname)
            try:
                text = _read_pdf_text(src)
                order, date_iso, gbp_amount = _extract_fields(text)
                new_name = _build_filename(order, gbp_amount, date_iso)

                if not new_name:
                    w.writerow([fname, "", order or "",
                                date_iso or "", gbp_amount or "", "SKIP_MISSING_KEYS"])
                    continue

                dst = os.path.join(output_dir, new_name)
                base, ext = os.path.splitext(dst)
                counter = 1
                final_dst = dst
                while os.path.exists(final_dst):
                    final_dst = f"{base}({counter}){ext}"
                    counter += 1

                shutil.copy2(src, final_dst)
                renamed += 1
                w.writerow([fname, os.path.basename(final_dst),
                            order or "", date_iso or "", gbp_amount or "", "RENAMED"])

            except Exception as e:
                w.writerow([fname, "", "", "", "", f"ERROR:{e}"])

    return total, renamed, log_path
