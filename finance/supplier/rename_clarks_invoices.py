# -*- coding: utf-8 -*-
"""
finance.clarks.rename_clarks_invoices
-------------------------------------
Clarks 专用：批量读取 PDF 发票，提取订单号、发票号、发票日期、
供货/收款日期（Date of supply / Payment received on）、含 VAT 的总额，
并按统一规则重命名后移动到输出目录，同时生成 rename_log.csv 供后续使用。

依赖:
    pip install PyPDF2

核心函数:
    rename_invoices(input_dir: str, output_dir: str) -> Tuple[int, int, str]
"""

from __future__ import annotations
import os
import re
import shutil
import csv
from typing import Optional, Tuple
from datetime import datetime

BRAND = "Clarks"
INCLUDE_INVOICE_ID = True
CURRENCY = "GBP"
CURRENCY_SYMBOL = "£"
LOG_FILENAME = "rename_log.csv"


# ---- Regex patterns ----
# Order No. 1013958359 / Order Number: 1014248215
ORDER_PATTERNS = [
    re.compile(r"Order\s+Number[:\s]+(\d{6,})", re.IGNORECASE),
    re.compile(r"Order\s+No\.?[:\s]+(\d{6,})", re.IGNORECASE),
]

# Retail Sales Invoice No. 6120 / Retail Sales Invoice no. OUT3367
INVOICE_PATTERNS = [
    re.compile(r"Retail\s+Sales\s+Invoice\s+No\.?\s*([A-Za-z0-9]+)", re.IGNORECASE),
]

# ➤ 这三个分别匹配：Date of invoice / Date of supply / Payment received on
DATE_OF_INVOICE_PATTERN = re.compile(
    r"Date\s+of\s+invoice\s+(\d{1,2}[./]\d{1,2}[./]\d{4})",
    re.IGNORECASE,
)

DATE_OF_SUPPLY_PATTERN = re.compile(
    r"Date\s+of\s+supply.*?(\d{1,2}[./]\d{1,2}[./]\d{4})",
    re.IGNORECASE,
)

PAYMENT_RECEIVED_PATTERN = re.compile(
    r"Payment\s+received\s+on\s+(\d{1,2}[./]\d{1,2}[./]\d{4})",
    re.IGNORECASE,
)

# 用于金额解析：TOTAL PAYABLE £153.50 ... 以及普通 £65.00 等
TOTAL_PAYABLE_PATTERN = re.compile(
    r"TOTAL\s+PAYABLE\s*£\s*([0-9][\d,]*\.\d{2})",
    re.IGNORECASE,
)


def _need_pypdf2():
    try:
        import PyPDF2  # type: ignore
        return PyPDF2
    except Exception:
        raise RuntimeError("Missing dependency PyPDF2. Please install with: pip install PyPDF2")


def _normalize_amount(amount_str: str) -> str:
    amt = amount_str.replace(",", "").strip()
    # 标准化为两位小数
    if re.match(r"^\d+(\.\d{2})?$", amt):
        return amt if "." in amt else f"{amt}.00"
    m = re.search(r"(\d+(?:\.\d{2}))", amt)
    return m.group(1) if m else amt


def _parse_date_to_iso(date_str: str) -> Optional[str]:
    """
    将类似 11.11.2025 / 03/11/2025 转成 YYYY-MM-DD
    """
    date_str = date_str.strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def _extract_total_gbp_clarks(text: str) -> Optional[str]:
    """
    提取 Clarks 发票上的含 VAT 总价：
    1) 优先匹配 “TOTAL PAYABLE £153.50”
    2) 如果没有 TOTAL PAYABLE，则收集全文所有 “£xx.xx”，取最大值
       - 单商品发票：最大值就是该商品总价（含 VAT）
       - 多商品发票：TOTAL PAYABLE 通常是所有金额中最大值
    """
    t = re.sub(r"\s+", " ", text).strip()

    # 1) 优先匹配 TOTAL PAYABLE
    m = TOTAL_PAYABLE_PATTERN.search(t)
    if m:
        return _normalize_amount(m.group(1))

    # 2) 收集所有 £amount，取最大
    amounts = [
        _normalize_amount(m.group(1))
        for m in re.finditer(r"£\s*([0-9][\d,]*\.\d{2})", t)
    ]
    if not amounts:
        return None

    try:
        max_amt = max(float(a) for a in amounts)
        return f"{max_amt:.2f}"
    except Exception:
        # 兜底：取最后一个
        return amounts[-1]


def _extract_fields(
    text: str,
) -> Tuple[
    Optional[str],  # order
    Optional[str],  # invoice
    Optional[str],  # invoice_date_iso
    Optional[str],  # txn_date_iso (payment/supply/invoice)
    Optional[str],  # gbp_amount
]:
    # 订单号
    order = None
    for pat in ORDER_PATTERNS:
        m = pat.search(text)
        if m:
            order = m.group(1)
            break

    # 发票号
    invoice = None
    for pat in INVOICE_PATTERNS:
        m = pat.search(text)
        if m:
            invoice = m.group(1)
            break

    # 发票日期（Date of invoice）
    invoice_date_iso = None
    m_inv = DATE_OF_INVOICE_PATTERN.search(text)
    if m_inv:
        invoice_date_iso = _parse_date_to_iso(m_inv.group(1))

    # ➤ 交易日期（优先用于对账 & 文件名）：
    # 1) Payment received on
    # 2) Date of supply (sale)
    # 3) Date of invoice（兜底）
    txn_date_iso = None

    m_pay = PAYMENT_RECEIVED_PATTERN.search(text)
    if m_pay:
        txn_date_iso = _parse_date_to_iso(m_pay.group(1))
    else:
        m_supply = DATE_OF_SUPPLY_PATTERN.search(text)
        if m_supply:
            txn_date_iso = _parse_date_to_iso(m_supply.group(1))
        else:
            txn_date_iso = invoice_date_iso  # 全部缺失就退回用发票日期

    # 金额（含 VAT 总价）
    gbp_amount = _extract_total_gbp_clarks(text)

    return order, invoice, invoice_date_iso, txn_date_iso, gbp_amount


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


def _build_filename(
    order: Optional[str],
    invoice: Optional[str],
    amount: Optional[str],
    txn_date_iso: Optional[str],
) -> Optional[str]:
    """
    文件名结构：
    Clarks_Invoice_ORDER_订单号_INV_发票号_£金额_YYYY-MM-DD.pdf

    ➤ 这里的日期使用“交易日期 txn_date_iso”：
       Payment received on > Date of supply > Date of invoice
    """
    if not order and not invoice:
        return None

    parts = [BRAND, "Invoice"]
    if order:
        parts.append(f"ORDER_{order}")
    if INCLUDE_INVOICE_ID and invoice:
        parts.append(f"INV_{invoice}")
    if amount:
        parts.append(f"{CURRENCY_SYMBOL}{amount}")
    if txn_date_iso:
        parts.append(txn_date_iso)

    return "_".join(parts) + ".pdf"


def rename_clarks_invoices(input_dir: str, output_dir: str) -> Tuple[int, int, str]:
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
            "old_name",
            "new_name",
            "order_number",
            "invoice_number",
            "invoice_date_iso",      # Date of invoice
            "txn_date_iso",          # ➤ Payment/Supply/Invoice (用于对账 & 文件名)
            "amount_gbp",
            "status",
        ])

        for fname in pdfs:
            src = os.path.join(input_dir, fname)
            try:
                text = _read_pdf_text(src)
                (
                    order,
                    invoice,
                    invoice_date_iso,
                    txn_date_iso,
                    gbp_amount,
                ) = _extract_fields(text)

                new_name = _build_filename(order, invoice, gbp_amount, txn_date_iso)

                if not new_name:
                    w.writerow([
                        fname, "",
                        order or "",
                        invoice or "",
                        invoice_date_iso or "",
                        txn_date_iso or "",
                        gbp_amount or "",
                        "SKIP_MISSING_KEYS",
                    ])
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
                w.writerow([
                    fname,
                    os.path.basename(final_dst),
                    order or "",
                    invoice or "",
                    invoice_date_iso or "",
                    txn_date_iso or "",
                    gbp_amount or "",
                    "RENAMED",
                ])

            except Exception as e:
                w.writerow([fname, "", "", "", "", "", "", f"ERROR:{e}"])

    return total, renamed, log_path
