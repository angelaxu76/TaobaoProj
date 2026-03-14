# -*- coding: utf-8 -*-
"""
finance.supplier.rename_amazon_invoices
----------------------------------------
Amazon UK 专用：批量读取 PDF 发票，提取订单号、发票号、发票日期、含 VAT 总额，
按统一规则重命名后复制到输出目录，同时生成 rename_log.csv。

Amazon UK 发票字段布局（示例）：
    Order #    026-0308585-5056357
    Invoice #  GB6WIDT3AEUI
    Invoice date / Delivery date   01 February 2026
    Total payable  £113.87

输出文件名格式（日期在前，便于按时间排序）：
    2026-02-01_Amazon_Invoice_ORDER_026-0308585-5056357_INV_GB6WIDT3AEUI_£113.87.pdf

依赖：
    pip install PyPDF2

核心函数：
    rename_amazon_invoices(input_dir, output_dir) -> Tuple[int, int, str]
"""

from __future__ import annotations
import os
import re
import shutil
import csv
from typing import Optional, Tuple
from datetime import datetime

BRAND              = "Amazon"
INCLUDE_INVOICE_ID = True
CURRENCY_SYMBOL    = "£"
LOG_FILENAME       = "rename_log.csv"

# ── Regex patterns ────────────────────────────────────────────────────────────

# 订单号：Order # 026-0308585-5056357
ORDER_PATTERN = re.compile(
    r"Order\s*#\s*([\d]{3}-[\d]{7}-[\d]{7})",
    re.IGNORECASE,
)
# 兜底：Amazon 订单号固定格式 NNN-NNNNNNN-NNNNNNN
ORDER_FALLBACK = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")

# 发票号：Invoice # GB6WIDT3AEUI
INVOICE_PATTERN = re.compile(
    r"Invoice\s*#\s*([A-Z0-9]{6,})",
    re.IGNORECASE,
)

# 发票日期：Invoice date / Delivery date   01 February 2026
DATE_PATTERN = re.compile(
    r"Invoice\s+date\s*/\s*Delivery\s+date\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)
# 兜底：Order date   31 January 2026
ORDER_DATE_PATTERN = re.compile(
    r"Order\s+date\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)

# 总价：Total payable £113.87 / Invoice total £113.87
TOTAL_PAYABLE_PATTERN = re.compile(
    r"Total\s+payable\s*£\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
INVOICE_TOTAL_PATTERN = re.compile(
    r"Invoice\s+total\s*£\s*([\d,]+\.\d{2})",
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
      - 01 February 2026  → %d %B %Y
      - 01 Feb 2026       → %d %b %Y
      - 31/01/2026        → %d/%m/%Y
      - 2026-01-31        → %Y-%m-%d
    """
    date_str = date_str.strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
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


def _extract_total(text: str) -> Optional[str]:
    """
    提取含 VAT 总价：
    1. 优先 "Total payable £113.87"
    2. 备用 "Invoice total £113.87"
    3. 兜底：全文最后一个 £ 金额
    """
    t = re.sub(r"\s+", " ", text).strip()

    m = TOTAL_PAYABLE_PATTERN.search(t)
    if m:
        return _normalize_amount(m.group(1))

    m = INVOICE_TOTAL_PATTERN.search(t)
    if m:
        return _normalize_amount(m.group(1))

    # 兜底：全文最后一个 £ 金额
    all_amounts = list(re.finditer(r"£\s*([\d,]+\.\d{2})", t))
    if all_amounts:
        return _normalize_amount(all_amounts[-1].group(1))

    return None


def _extract_fields(
    text: str,
) -> Tuple[
    Optional[str],  # order_number
    Optional[str],  # invoice_number
    Optional[str],  # date_iso
    Optional[str],  # gbp_amount
]:
    # 订单号
    order = None
    m = ORDER_PATTERN.search(text)
    if m:
        order = m.group(1)
    if not order:
        m = ORDER_FALLBACK.search(text)
        if m:
            order = m.group(1)

    # 发票号
    invoice = None
    m = INVOICE_PATTERN.search(text)
    if m:
        invoice = m.group(1).upper()

    # 日期（优先发票日期，备用订单日期）
    date_iso = None
    m = DATE_PATTERN.search(text)
    if m:
        date_iso = _parse_date_to_iso(m.group(1))
    if not date_iso:
        m = ORDER_DATE_PATTERN.search(text)
        if m:
            date_iso = _parse_date_to_iso(m.group(1))

    # 总价
    gbp_amount = _extract_total(text)

    return order, invoice, date_iso, gbp_amount


def _build_filename(
    order: Optional[str],
    invoice: Optional[str],
    amount: Optional[str],
    date_iso: Optional[str],
) -> Optional[str]:
    """
    日期在最前，便于按时间排序：
    2026-02-01_Amazon_Invoice_ORDER_026-0308585-5056357_INV_GB6WIDT3AEUI_£113.87.pdf
    """
    if not order and not invoice:
        return None
    parts = []
    if date_iso:
        parts.append(date_iso)
    parts.extend([BRAND, "Invoice"])
    if order:
        parts.append(f"ORDER_{order}")
    if INCLUDE_INVOICE_ID and invoice:
        parts.append(f"INV_{invoice}")
    if amount:
        parts.append(f"{CURRENCY_SYMBOL}{amount}")
    return "_".join(parts) + ".pdf"


# ── 主入口 ────────────────────────────────────────────────────────────────────

def rename_amazon_invoices(input_dir: str, output_dir: str) -> Tuple[int, int, str]:
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
            "order_number", "invoice_number",
            "date_iso", "amount_gbp", "status",
        ])

        for fname in pdfs:
            src = os.path.join(input_dir, fname)
            try:
                text = _read_pdf_text(src)
                order, invoice, date_iso, gbp_amount = _extract_fields(text)
                new_name = _build_filename(order, invoice, gbp_amount, date_iso)

                if not new_name:
                    w.writerow([fname, "", order or "", invoice or "",
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
                            order or "", invoice or "",
                            date_iso or "", gbp_amount or "", "RENAMED"])

            except Exception as e:
                w.writerow([fname, "", "", "", "", "", f"ERROR:{e}"])

    return total, renamed, log_path
