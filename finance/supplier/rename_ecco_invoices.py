# -*- coding: utf-8 -*-
"""
finance.supplier.rename_ecco_invoices
--------------------------------------
ECCO 专用：批量读取 PDF 发票，提取订单号、发票号、发票日期、含 VAT 总额，
按统一规则重命名后复制到输出目录，同时生成 rename_log.csv。

ECCO 发票字段布局（示例）：
    Number   SI-0246460
    Order    GB000016766
    Invoice date   01/12/2025
    Payment date   01/12/2025
    Order date     30/11/2025
    ...
    Total    3.00   44.00   30.33   181.95   GBP

输出文件名格式：
    ECCO_Invoice_ORDER_GB000016766_INV_SI-0246460_£181.95_2025-12-01.pdf

依赖：
    pip install PyPDF2

核心函数：
    rename_ecco_invoices(input_dir, output_dir) -> Tuple[int, int, str]
"""

from __future__ import annotations
import os
import re
import shutil
import csv
from typing import Optional, Tuple
from datetime import datetime

BRAND            = "ECCO"
INCLUDE_INVOICE_ID = True
CURRENCY_SYMBOL  = "£"
LOG_FILENAME     = "rename_log.csv"

# ── Regex patterns ────────────────────────────────────────────────────────────

# 发票号：独立 "Number" 行，值形如 SI-0246460
# 用 MULTILINE 匹配行首，避免误命中其他含 "number" 的行
INVOICE_PATTERN = re.compile(
    r"(?:^|\n)\s*Number\s+(SI-\d+)",
    re.IGNORECASE | re.MULTILINE,
)
# 兜底：直接找 SI- 前缀
INVOICE_FALLBACK = re.compile(r"\b(SI-\d{5,})\b", re.IGNORECASE)

# 订单号：独立 "Order" 行，值形如 GB000016766
# 明确要求值以 GB 开头的纯字母+数字组合，不会误命中 "Order date"
ORDER_PATTERN = re.compile(
    r"(?:^|\n)\s*Order\s+(GB\d{6,})\b",
    re.IGNORECASE | re.MULTILINE,
)

# 发票日期：Invoice date DD/MM/YYYY
INVOICE_DATE_PATTERN = re.compile(
    r"Invoice\s+date\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
    re.IGNORECASE,
)

# 支付日期（备用）
PAYMENT_DATE_PATTERN = re.compile(
    r"Payment\s+date\s+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
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
    """将 DD/MM/YYYY 或其他常见格式转为 YYYY-MM-DD。"""
    date_str = date_str.strip()
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"):
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


def _extract_total_gbp(text: str) -> Optional[str]:
    """
    ECCO 发票 Total 行格式：
        Total  <qty>  <discount>  <vat>  <total_gbp>  GBP
    同一行最后出现的 GBP 金额即为含 VAT 总价。

    策略：
    1. 取最后一个 "Total" 行，匹配其后第一个 NN.NN GBP 组合
    2. 兜底：全文最后一个出现的 GBP 金额
    """
    t = re.sub(r"\s+", " ", text).strip()

    # 策略 1：最后一个 Total 行之后的第一个 "数字 GBP"
    totals = list(re.finditer(r"\bTotal\b", t, re.IGNORECASE))
    if totals:
        tail = t[totals[-1].end():]
        m = re.search(r"([0-9][\d,]*\.\d{2})\s+GBP\b", tail, re.IGNORECASE)
        if m:
            return _normalize_amount(m.group(1))

    # 策略 2：全文最后一个 GBP 金额
    all_gbp = list(re.finditer(r"([0-9][\d,]*\.\d{2})\s+GBP\b", t, re.IGNORECASE))
    if all_gbp:
        return _normalize_amount(all_gbp[-1].group(1))

    return None


def _extract_fields(
    text: str,
) -> Tuple[
    Optional[str],  # order_number
    Optional[str],  # invoice_number
    Optional[str],  # invoice_date_iso
    Optional[str],  # gbp_amount
]:
    # 订单号
    order = None
    m = ORDER_PATTERN.search(text)
    if m:
        order = m.group(1)

    # 发票号
    invoice = None
    m = INVOICE_PATTERN.search(text)
    if m:
        invoice = m.group(1)
    if not invoice:
        m = INVOICE_FALLBACK.search(text)
        if m:
            invoice = m.group(1)

    # 发票日期（优先 Invoice date，备用 Payment date）
    date_iso = None
    m = INVOICE_DATE_PATTERN.search(text)
    if m:
        date_iso = _parse_date_to_iso(m.group(1))
    if not date_iso:
        m = PAYMENT_DATE_PATTERN.search(text)
        if m:
            date_iso = _parse_date_to_iso(m.group(1))

    # 含 VAT 总额
    gbp_amount = _extract_total_gbp(text)

    return order, invoice, date_iso, gbp_amount


def _build_filename(
    order: Optional[str],
    invoice: Optional[str],
    amount: Optional[str],
    date_iso: Optional[str],
) -> Optional[str]:
    """
    日期在最前，便于按时间排序：
    2025-12-01_ECCO_Invoice_ORDER_GB000016766_INV_SI-0246460_£181.95.pdf
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

def rename_ecco_invoices(input_dir: str, output_dir: str) -> Tuple[int, int, str]:
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
            "invoice_date_iso", "amount_gbp", "status",
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
