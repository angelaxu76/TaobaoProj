# -*- coding: utf-8 -*-
"""
finance.camper.rename_camper_invoices
-------------------------------------
Camper 专用：批量读取 PDF 发票，提取订单号、发票号、日期、GBP 总额，
并按统一规则重命名后移动到输出目录，同时生成 rename_log.csv 供后续 pipeline 使用。

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

BRAND = "Camper"
INCLUDE_INVOICE_ID = True
CURRENCY = "GBP"
CURRENCY_SYMBOL = "£"
LOG_FILENAME = "rename_log.csv"

# ---- Regex patterns ----
ORDER_PATTERNS = [
    re.compile(r"Order\s*Number[:\s]+(\d{6,})", re.IGNORECASE),
    re.compile(r"Order\s*#[:\s]+(\d{6,})", re.IGNORECASE),
]

INVOICE_PATTERNS = [
    re.compile(r"Invoice\s*Number[:\s]+([A-Za-z0-9-]{6,})", re.IGNORECASE),
    re.compile(r"Invoice\s*No\.?[:\s]+([A-Za-z0-9-]{6,})", re.IGNORECASE),
]

DATE_LABELLED_PATTERNS = [
    (re.compile(r"Invoice\s*Date[:\s]+(\d{2}[./-]\d{2}[./-]\d{4})", re.IGNORECASE),
     ["%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"]),
    (re.compile(r"Invoice\s*Date[:\s]+(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
     ["%Y-%m-%d"]),
    (re.compile(r"Invoice\s*Date[:\s]+([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", re.IGNORECASE),
     ["%B %d, %Y", "%b %d, %Y"]),
]

GBP_TOTAL_PATTERNS = [
    re.compile(r"Total\s+([0-9][\d,]*\.\d{2})\s*GBP", re.IGNORECASE),
    re.compile(r"\bGBP\s*([0-9][\d,]*\.\d{2})\b", re.IGNORECASE),
]


def _need_pypdf2():
    try:
        import PyPDF2  # type: ignore
        return PyPDF2
    except Exception:
        raise RuntimeError("Missing dependency PyPDF2. Please install with: pip install PyPDF2")


def _normalize_amount(amount_str: str) -> str:
    amt = amount_str.replace(",", "").strip()
    if re.match(r"^\d+(\.\d{2})?$", amt):
        return amt if "." in amt else f"{amt}.00"
    m = re.search(r"(\d+(?:\.\d{2}))", amt)
    return m.group(1) if m else amt


def _parse_date_to_iso(date_str: str) -> Optional[str]:
    date_str = date_str.strip()
    for _pat, fmts in DATE_LABELLED_PATTERNS:
        for fmt in fmts:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def _extract_fields(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    order = None
    for pat in ORDER_PATTERNS:
        m = pat.search(text)
        if m:
            order = m.group(1)
            break

    invoice = None
    for pat in INVOICE_PATTERNS:
        m = pat.search(text)
        if m:
            invoice = m.group(1)
            break

    date_iso = None
    date_raw = None
    for pat, _ in DATE_LABELLED_PATTERNS:
        m = pat.search(text)
        if m:
            date_raw = m.group(1)
            break
    if date_raw:
        date_iso = _parse_date_to_iso(date_raw)

    gbp_amount = _extract_total_gbp(text)

    return order, invoice, date_iso, gbp_amount


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

def _extract_total_gbp(text: str) -> Optional[str]:
    """
    识别含 VAT 的总价（Total ... GBP/£），
    1) 避免命中 Sub-total
    2) 如果有多个“Total”（如表头 VAT Total），取“最后一个 Total”后的金额
    3) 兜底：取全文最后一个 GBP 金额
    """
    # 压缩连续空白（空格、换行、制表符）以消除跨行影响
    t = re.sub(r"\s+", " ", text).strip()

    # 先尝试直接匹配“Total 金额 GBP”，并避免命中 "Sub-total"
    m = re.search(r"(?<!Sub-)\bTotal\b\s*[:\-]?\s*([0-9][\d,]*\.\d{2})\s*(?:GBP|£)\b",
                  t, re.IGNORECASE)
    if m:
        amt = m.group(1).replace(",", "").strip()
        return re.search(r"(\d+(?:\.\d{2}))", amt).group(1)

    # 找到“最后一个 Total”标签，然后在其后搜索第一个 GBP 金额
    totals = list(re.finditer(r"\bTotal\b", t, re.IGNORECASE))
    if totals:
        tail = t[totals[-1].end():]
        m2 = re.search(r"([0-9][\d,]*\.\d{2})\s*(?:GBP|£)\b", tail, re.IGNORECASE)
        if m2:
            amt = m2.group(1).replace(",", "").strip()
            return re.search(r"(\d+(?:\.\d{2}))", amt).group(1)

    # 兜底：全文最后一个 GBP/£ 金额
    all_gbp = list(re.finditer(r"([0-9][\d,]*\.\d{2})\s*(?:GBP|£)\b", t, re.IGNORECASE))
    if all_gbp:
        amt = all_gbp[-1].group(1).replace(",", "").strip()
        m3 = re.search(r"(\d+(?:\.\d{2}))", amt)
        return m3.group(1) if m3 else amt

    return None






def _build_filename(order: Optional[str], invoice: Optional[str],
                    amount: Optional[str], date_iso: Optional[str]) -> Optional[str]:
    if not order and not invoice:
        return None
    parts = [BRAND, "Invoice"]
    if order:
        parts.append(f"ORDER_{order}")
    if INCLUDE_INVOICE_ID and invoice:
        parts.append(f"INV_{invoice}")
    if amount:
        parts.append(f"{CURRENCY_SYMBOL}{amount}")
    if date_iso:
        parts.append(date_iso)
    return "_".join(parts) + ".pdf"


def rename_invoices(input_dir: str, output_dir: str) -> Tuple[int, int, str]:
    """读取 input_dir 下所有 PDF，重命名后移动到 output_dir。
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
        w.writerow(["old_name", "new_name", "order_number", "invoice_number",
                    "invoice_date_iso", "amount_gbp", "status"])

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
                w.writerow([fname, os.path.basename(final_dst), order or "",
                            invoice or "", date_iso or "", gbp_amount or "", "RENAMED"])

            except Exception as e:
                w.writerow([fname, "", "", "", "", "", f"ERROR:{e}"])

    return total, renamed, log_path
