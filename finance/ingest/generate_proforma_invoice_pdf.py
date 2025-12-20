\
# -*- coding: utf-8 -*-
r"""
Generate a Proforma Invoice (Advance Payment) as a signed PDF.

Usage examples:
  python generate_proforma_invoice_pdf.py --amount 1000 --date 2025-11-12
  python generate_proforma_invoice_pdf.py --amount 3900 --date 2025-11-20 --invoice-no PI-2025-1120

Optional:
  --signature-image "<path-to-signature-image.png>"

Notes:
- Uses finance_config.FINANCE_EES for exporter/consignee/bank if available.
- Keeps wording minimal (no "services", no "fees") to reduce KYC keyword risk.
"""


import argparse
from pathlib import Path
from datetime import datetime, date
import importlib.util

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors


def _load_finance_ees():
    # Expect finance_config.py in the same folder as this script OR in PYTHONPATH
    here = Path(__file__).resolve().parent
    local_cfg = here / "finance_config.py"
    if local_cfg.exists():
        spec = importlib.util.spec_from_file_location("finance_config", str(local_cfg))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "FINANCE_EES", None)

    try:
        import finance_config  # type: ignore
        return getattr(finance_config, "FINANCE_EES", None)
    except Exception:
        return None


def money_fmt(x: float) -> str:
    return f"{x:,.2f}"


def draw_wrapped(c, text, x, y, width, leading=12, font="Helvetica", size=10):
    c.setFont(font, size)
    words = text.split()
    line = ""
    lines = []
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, font, size) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    for ln in lines:
        c.drawString(x, y, ln)
        y -= leading
    return y


def create_pi_pdf(
    out_path: Path,
    amount_gbp: float,
    inv_date: date,
    invoice_no: str,
    exporter: dict,
    consignee: dict,
    bank: dict,
    sign_name: str,
    sign_title: str,
    signature_image_path: str | None = None,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    margin = 18 * mm
    x0 = margin
    y = h - margin

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, y, "PROFORMA INVOICE (ADVANCE PAYMENT)")
    y -= 14 * mm

    # Invoice details (right)
    right_x = w - margin - 70 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(right_x, y, "Invoice Details")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(right_x, y, f"Invoice No.: {invoice_no}")
    y -= 5 * mm
    c.drawString(right_x, y, f"Invoice Date: {inv_date.isoformat()}")
    y -= 5 * mm
    c.drawString(right_x, y, "Currency: GBP")

    # Exporter
    left_block_y = h - margin - 24 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0, left_block_y, "Exporter (Seller)")
    c.setFont("Helvetica", 10)
    y2 = left_block_y - 5 * mm
    y2 = draw_wrapped(c, f"Company Name: {exporter.get('name','')}", x0, y2, 92 * mm)
    y2 = draw_wrapped(c, f"Address: {exporter.get('address','')}", x0, y2, 92 * mm)

    # Consignee
    y2 -= 2 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0, y2, "Consignee (Buyer)")
    c.setFont("Helvetica", 10)
    y2 -= 5 * mm
    y2 = draw_wrapped(c, f"Company Name: {consignee.get('name','')}", x0, y2, 92 * mm)
    y2 = draw_wrapped(c, f"Address: {consignee.get('address','')}", x0, y2, 92 * mm)

    # Table
    y_table_top = min(y2, y) - 10 * mm
    table_x = x0
    table_w = w - 2 * margin
    row_h = 10 * mm

    c.setFillColor(colors.lightgrey)
    c.rect(table_x, y_table_top - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.rect(table_x, y_table_top - row_h * 2, table_w, row_h * 2, fill=0, stroke=1)

    col_desc = table_w * 0.72
    col_amt = table_w - col_desc

    c.setFont("Helvetica-Bold", 10)
    c.drawString(table_x + 3 * mm, y_table_top - 7 * mm, "Description")
    c.drawRightString(table_x + col_desc + col_amt - 3 * mm, y_table_top - 7 * mm, "Amount (GBP)")

    c.setFont("Helvetica", 10)
    c.drawString(table_x + 3 * mm, y_table_top - row_h - 7 * mm, "Advance payment for goods procurement")
    c.drawRightString(table_x + col_desc + col_amt - 3 * mm, y_table_top - row_h - 7 * mm, money_fmt(amount_gbp))

    y_after_table = y_table_top - row_h * 2 - 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x0, y_after_table, f"Total Amount: GBP {money_fmt(amount_gbp)}")
    y_after_table -= 10 * mm

    # Bank
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0, y_after_table, "Bank Payment Details")
    y_after_table -= 6 * mm
    c.setFont("Helvetica", 10)

    bank_lines = []
    if bank.get("bank_name"):
        bank_lines.append(f"Bank: {bank.get('bank_name')}")
    if bank.get("account_name"):
        bank_lines.append(f"Account Name: {bank.get('account_name')}")
    if bank.get("sort_code"):
        bank_lines.append(f"Sort Code: {bank.get('sort_code')}")
    if bank.get("account_no"):
        bank_lines.append(f"Account Number: {bank.get('account_no')}")
    if bank.get("iban"):
        bank_lines.append(f"IBAN: {bank.get('iban')}")
    if bank.get("swift"):
        bank_lines.append(f"SWIFT/BIC: {bank.get('swift')}")

    if not bank_lines:
        bank_lines.append("Bank details available upon request.")

    for ln in bank_lines:
        y_after_table = draw_wrapped(c, ln, x0, y_after_table, w - 2 * margin, leading=12, font="Helvetica", size=10)

    # Signature block
    y_sig = 35 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0, y_sig + 40, "For and on behalf of EMINZORA TRADE LTD")
    c.setFont("Helvetica", 10)
    c.drawString(x0, y_sig + 26, "Authorised Signature:")

    if signature_image_path and Path(signature_image_path).exists():
        try:
            c.drawImage(signature_image_path, x0 + 40 * mm, y_sig + 12, width=45 * mm, height=15 * mm, mask='auto')
        except Exception:
            pass
    else:
        c.line(x0 + 40 * mm, y_sig + 18, x0 + 95 * mm, y_sig + 18)

    c.drawString(x0, y_sig, f"Name: {sign_name}")
    c.drawString(x0, y_sig - 12, f"Title: {sign_title}")
    c.drawString(x0, y_sig - 24, f"Date: {inv_date.isoformat()}")

    c.showPage()
    c.save()
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--amount", type=float, required=True, help="Total amount in GBP, e.g. 1000 or 3900")
    parser.add_argument("--date", type=str, required=True, help="Invoice date, YYYY-MM-DD")
    parser.add_argument("--invoice-no", type=str, default=None, help="Invoice No., default: PI-YYYYMMDD")
    parser.add_argument("--out", type=str, default=None, help="Output PDF path (optional)")
    parser.add_argument("--signature-image", type=str, default=None, help="Optional signature PNG path")
    parser.add_argument("--sign-name", type=str, default="XIAODAN MA")
    parser.add_argument("--sign-title", type=str, default="Director, EMINZORA TRADE LTD")
    args = parser.parse_args()

    inv_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    invoice_no = args.invoice_no or f"PI-{inv_date.strftime('%Y%m%d')}"

    out_path = Path(args.out) if args.out else Path.cwd() / f"ProformaInvoice_AdvancePayment_{invoice_no}_{money_fmt(args.amount).replace(',','')}.pdf"

    finance_ees = _load_finance_ees()
    if not finance_ees:
        raise SystemExit("Cannot load FINANCE_EES. Put finance_config.py next to this script or in PYTHONPATH.")

    exporter = finance_ees.get("exporter", {})
    consignee = finance_ees.get("consignee", {})
    bank = finance_ees.get("bank", {})

    create_pi_pdf(
        out_path=out_path,
        amount_gbp=float(args.amount),
        inv_date=inv_date,
        invoice_no=invoice_no,
        exporter=exporter,
        consignee=consignee,
        bank=bank,
        sign_name=args.sign_name,
        sign_title=args.sign_title,
        signature_image_path=args.signature_image,
    )

    print(f"[OK] Generated: {out_path}")

from datetime import date
from pathlib import Path
from typing import Optional

from finance_config import FINANCE_EES


def generate_pi_simple(
    amount_gbp: float,
    inv_date: date,
    *,
    out_dir: Optional[Path] = None,
    invoice_no: Optional[str] = None,
    signature_image_path: Optional[str] = None,
):
    invoice_no = invoice_no or f"PI-{inv_date.strftime('%Y%m%d')}"
    out_dir = out_dir or Path.cwd()

    sig_cfg = FINANCE_EES.get("signature", {})
    if signature_image_path is None:
        signature_image_path = sig_cfg.get("image_path")

    out_path = out_dir / f"ProformaInvoice_AdvancePayment_{invoice_no}_{amount_gbp:.0f}.pdf"

    return create_pi_pdf(
        out_path=out_path,
        amount_gbp=amount_gbp,
        inv_date=inv_date,
        invoice_no=invoice_no,
        exporter=FINANCE_EES["exporter"],
        consignee=FINANCE_EES["consignee"],
        bank=FINANCE_EES["bank"],
        sign_name=sig_cfg.get("sign_name", "XIAODAN MA"),
        sign_title=sig_cfg.get("sign_title", "Director, EMINZORA TRADE LTD"),
        signature_image_path=signature_image_path,
    )



if __name__ == "__main__":
    main()
