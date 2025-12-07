"""
Generate Export Evidence Summary PDF + Commercial Invoice PDF
Compliant with HMRC Notice 703 (Zero-rated Export)
Author: EMINZORA Compliance Automation
"""

import os
import sys
import re
import datetime as dt

import psycopg2
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# 让脚本能找到根目录配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import PGSQL_CONFIG as GLOBAL_PGSQL_CONFIG
from finance_config import FINANCE_EES

# ---------- Font ----------
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

# ---------- Config ----------
CONFIG = {
    # 注意：这里已经改成 _UK 版本的路径
    "output_dir": r"D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs",
    "exporter": FINANCE_EES["exporter"],
    "consignee": FINANCE_EES["consignee"],
    "carrier": FINANCE_EES["logistics"]["carrier"],
    "route": FINANCE_EES["logistics"]["route"],
    "declaration": FINANCE_EES["declaration"],
    "db": {**GLOBAL_PGSQL_CONFIG, "connect_timeout": 5},
}

# ---------- Data helpers ----------
def _clean_desc(s: str) -> str:
    if not s:
        return ""
    t = s.strip()

    # 统一品牌大小写
    repl = {
        r"\bbarbour\b": "Barbour",
        r"\bclarks\b": "Clarks",
        r"\bcamper\b": "Camper",
        r"\bgeox\b": "GEOX",
        r"\becco\b": "ECCO",
    }
    for pat, rep in repl.items():
        t = re.sub(pat, rep, t, flags=re.I)

    # 去重品牌词（如 "Barbour Barbour" -> "Barbour"）
    t = re.sub(r"\b(Barbour|Clarks|Camper|GEOX|ECCO)\b(\s+\1\b)+", r"\1", t)

    # 去掉常见噪声/口水词
    t = re.sub(r"\blook\s+step\b", "", t, flags=re.I)
    t = re.sub(r"\bk\s*-\b", "", t, flags=re.I)
    t = re.sub(r"\byards?\s*\d+\b", "", t, flags=re.I)
    t = re.sub(r"\bsize\s*\d+\b", "", t, flags=re.I)
    t = re.sub(r"\b\d+(\.\d+)?\s*cm\b", "", t, flags=re.I)
    t = re.sub(r"\bcm\b", "", t, flags=re.I)
    t = re.sub(r"\bchnx\b", "", t, flags=re.I)

    # 合并空白
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def _prepare_items(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗 + 聚合明细：
    - 合并相同 sku + 描述
    - 计算 unit_value / total_value
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["skuid", "product_description", "quantity", "unit_value", "total_value"])

    df = df.copy()
    df["skuid"] = df["skuid"].astype(str).str.strip()
    df["product_description"] = df["product_description"].map(_clean_desc)

    if "quantity" not in df.columns:
        df["quantity"] = 1

    if "total_value" not in df.columns:
        # 如果只有 value_gbp，就当成 total_value
        if "value_gbp" in df.columns:
            df["total_value"] = df["value_gbp"]
        else:
            df["total_value"] = 0.0

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce").fillna(0.0).astype(float)

    grouped = (
        df.groupby(["skuid", "product_description"], dropna=False)[["quantity", "total_value"]]
        .sum()
        .reset_index()
    )

    grouped["unit_value"] = (
        grouped["total_value"] / grouped["quantity"].replace(0, pd.NA)
    ).fillna(0.0).round(2)

    return grouped[["skuid", "product_description", "quantity", "unit_value", "total_value"]]


# ---------- DB helpers ----------
def _get_conn():
    return psycopg2.connect(**CONFIG["db"])


def fetch_export_summary(invoice_no: str) -> dict | None:
    """
    从 export_shipments_summary 取汇总信息
    """
    sql = """
    SELECT
        uk_invoice_no,
        uk_invoice_date,
        folder_name,
        currency,
        total_value_gbp,
        total_quantity,
        total_gross_weight_kg,
        tracking_no,
        poe_id,
        poe_mrn,
        poe_office,
        poe_date
    FROM public.export_shipments_summary
    WHERE uk_invoice_no = %s
    """
    conn = _get_conn()
    try:
        df = pd.read_sql(sql, conn, params=[invoice_no])
    finally:
        conn.close()

    if df.empty:
        return None
    return df.iloc[0].to_dict()


def fetch_itemized_goods(invoice_no: str) -> pd.DataFrame:
    """
    从 export_shipments 取明细
    """
    sql = """
    SELECT skuid, product_description, quantity, value_gbp
    FROM public.export_shipments
    WHERE uk_invoice_no = %s
    """
    conn = _get_conn()
    try:
        df = pd.read_sql(sql, conn, params=[invoice_no])
    finally:
        conn.close()

    if "value_gbp" in df.columns:
        df["total_value"] = df["value_gbp"]
    return df


# ---------- Common PDF helpers ----------
def _nz(v, fb="N/A"):
    s = str(v or "").strip()
    return s or fb


def _fmt_gbp(v: float) -> str:
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return "0.00"


# ---------- Export Evidence Summary ----------
def generate_export_evidence_pdf(invoice_no: str, output_dir: str | None = None):
    data_summary = fetch_export_summary(invoice_no)
    if not data_summary:
        print(f"[WARN] Invoice {invoice_no} not found.")
        return

    items_raw = fetch_itemized_goods(invoice_no)
    items = _prepare_items(items_raw)

    # 输出目录：优先使用外部传入的 output_dir
    base_dir = output_dir or CONFIG["output_dir"]
    folder_name = data_summary.get("folder_name") or "UNKNOWN"
    out_dir = os.path.join(base_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"ExportEvidenceSummary_{invoice_no}.pdf")

    # 样式
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=1.8*cm, bottomMargin=1.5*cm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title_style = ParagraphStyle(
        "title", parent=normal,
        fontSize=16, leading=20,
        alignment=1,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "h2", parent=normal,
        fontSize=12, leading=15,
        spaceBefore=8, spaceAfter=6,
    )
    desc_style = ParagraphStyle(
        "desc",
        fontName="HeiseiKakuGo-W5",
        fontSize=8, leading=10,
        wordWrap="CJK",
    )

    story = []

    # ---------- Title ----------
    story.append(Paragraph(
        "<b>Export Evidence Summary (VAT Zero-Rated Export)</b>"
        "<br/><font size=9>(Compliant with HMRC Notice 703)</font>",
        title_style,
    ))

    # ---------- Exporter & Consignee ----------
    exp, con = CONFIG["exporter"], CONFIG["consignee"]

    exporter_info = f"""
    <b>Exporter (UK)</b><br/>
    {exp['name']}<br/>{exp['address']}<br/>
    Company No.: {_nz(exp.get('company_no'))}<br/>
    VAT No.: {_nz(exp.get('vat_no'))}<br/>
    EORI: {_nz(exp.get('eori_no'))}<br/>
    Phone: {_nz(exp.get('phone'))}<br/>
    Email: {_nz(exp.get('email'))}
    """
    consignee_info = f"""
    <b>Consignee (Overseas Entity)</b><br/>
    {con['name']}<br/>{con['address']}<br/>
    Phone: {_nz(con.get('phone'))}<br/>
    Email: {_nz(con.get('email'))}<br/>
    Jurisdiction: Hong Kong SAR
    """

    t_party = Table(
        [[Paragraph(exporter_info, normal), Paragraph(consignee_info, normal)]],
        colWidths=[8*cm, 8*cm],
    )
    t_party.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
    ]))
    story.extend([t_party, Spacer(1, 8)])

    # ---------- Shipment & Invoice Details ----------
    story.append(Paragraph("<b>Shipment & Invoice Details</b>", h2))

    tbl_data = [
        ["Internal Reference No.", invoice_no],
        ["Date", _nz(data_summary.get("uk_invoice_date"))],
        ["Currency", _nz(data_summary.get("currency"), "GBP")],
        ["Total Value (GBP)", _fmt_gbp(data_summary.get("total_value_gbp") or 0)],
        ["Total Quantity", f"{int(float(data_summary.get('total_quantity') or 0))}"],
        ["Total Gross Weight (kg)", _nz(data_summary.get("total_gross_weight_kg"))],
        ["Carrier", CONFIG["carrier"]],
        ["Export Route", CONFIG["route"]],
        ["Tracking Reference", _nz(data_summary.get("tracking_no"), "N/A")],
    ]

    tbl = Table(tbl_data, colWidths=[5*cm, 10*cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([tbl, Spacer(1, 8)])

    # ---------- Itemized Goods List ----------
    story.append(Paragraph("<b>Itemized Goods List (Summary)</b>", h2))

    item_rows = [["Product Code / SKU", "Goods Description", "Quantity", "Unit Value (GBP)", "Total Value (GBP)"]]
    total_val, total_qty = 0.0, 0

    for _, r in items.iterrows():
        q = int(r.get("quantity", 0) or 0)
        if q <= 0:
            continue

        tv = float(r.get("total_value", 0.0) or 0.0)
        uv = float(r.get("unit_value", 0.0) or 0.0)
        total_qty += q
        total_val += tv

        item_rows.append([
            str(r.get("skuid") or ""),
            Paragraph(str(r.get("product_description") or ""), desc_style),
            f"{q}",
            _fmt_gbp(uv),
            _fmt_gbp(tv),
        ])

    # 合计行
    item_rows.append([
        "",
        Paragraph("<b>TOTALS</b>", desc_style),
        Paragraph(f"<b>{total_qty}</b>", desc_style),
        "",
        Paragraph(f"<b>{_fmt_gbp(total_val)}</b>", desc_style),
    ])

    goods_table = Table(
        item_rows,
        colWidths=[3.2*cm, 7.4*cm, 2.1*cm, 2.6*cm, 2.8*cm],
    )
    goods_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (2, 1), (-1, -2), "CENTER"),
        ("ALIGN", (3, 1), (4, -2), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
    ]))
    story.extend([
        goods_table,
        Paragraph(
            "<font size=8><i>Supporting UK supplier purchase invoices for these goods "
            "are retained separately in the accounting records "
            "(folder: 03_Purchase_Records/01_Supplier_Invoices) and can be provided "
            "to HMRC upon request.</i></font>",
            normal,
        ),
        Spacer(1, 10),
    ])

    # ---------- Proof of Export ----------
    story.append(Paragraph("<b>Proof of Export (POE)</b>", h2))

    poe_tbl = [
        ["POE ID", _nz(data_summary.get("poe_id"))],
        ["MRN", _nz(data_summary.get("poe_mrn"))],
        ["Office of Exit", _nz(data_summary.get("poe_office"))],
        ["Date of Export", _nz(data_summary.get("poe_date"))],
        ["Evidence Type", "POE PDF + Internal Reference Summary"],
        ["Attachments", Paragraph(
            f"1. POE_{data_summary.get('poe_date','')}.pdf<br/>"
            f"2. Internal_Reference_{invoice_no}.pdf",
            desc_style,
        )],
    ]

    poe_table = Table(poe_tbl, colWidths=[5*cm, 10*cm])
    poe_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([poe_table, Spacer(1, 12)])

    # ---------- Declaration ----------
    story.append(Paragraph("<b>Declaration</b>", h2))
    story.append(Paragraph(CONFIG["declaration"], normal))
    story.append(Paragraph(
        "Supporting UK supplier purchase invoices for the goods listed in this shipment "
        "are retained separately in the accounting records (03_Purchase_Records/01_Supplier_Invoices) "
        "and can be provided to HMRC on request.",
        normal,
    ))

    story.extend([
        Spacer(1, 30),
        Paragraph("Prepared by: _________________________________", normal),
        Spacer(1, 10),
        Paragraph("Position: Director, EMINZORA TRADE LTD", normal),
        Spacer(1, 10),
        Paragraph("Date: _______________________________________", normal),
        Spacer(1, 10),
        Paragraph("Signature: __________________________________", normal),
        Spacer(1, 40),
    ])

    doc.build(story)
    print(f"[OK] Export Evidence Summary generated: {pdf_path}")


# ---------- Commercial Invoice ----------
def generate_commercial_invoice_pdf(invoice_no: str, output_dir: str | None = None):
    """
    Generate Commercial Invoice (CI) PDF for a given internal invoice_no.
    """
    data_summary = fetch_export_summary(invoice_no)
    if not data_summary:
        print(f"[WARN] Invoice {invoice_no} not found in export_shipments_summary.")
        return

    items_raw = fetch_itemized_goods(invoice_no)
    items = _prepare_items(items_raw)

    base_dir = output_dir or CONFIG["output_dir"]
    folder_name = data_summary.get("folder_name") or "UNKNOWN"
    out_dir = os.path.join(base_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"CommercialInvoice_{invoice_no}.pdf")

    # PDF 基础
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=1.8*cm, bottomMargin=1.5*cm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title_style = ParagraphStyle(
        "title", parent=normal,
        fontSize=16, leading=20,
        alignment=1,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "h2", parent=normal,
        fontSize=12, leading=15,
        spaceBefore=8, spaceAfter=6,
    )
    desc_style = ParagraphStyle(
        "desc",
        fontName="HeiseiKakuGo-W5",
        fontSize=8, leading=10,
        wordWrap="CJK",
    )

    story: list = []

    # ---------- Title ----------
    story.append(Paragraph("<b>Commercial Invoice</b>", title_style))

    exp, con = CONFIG["exporter"], CONFIG["consignee"]
    exporter_info = f"""
    <b>Seller (Exporter, UK)</b><br/>
    {exp['name']}<br/>{exp['address']}<br/>
    Company No.: {_nz(exp.get('company_no'))}<br/>
    VAT No.: {_nz(exp.get('vat_no'))}<br/>
    EORI: {_nz(exp.get('eori_no'))}<br/>
    Phone: {_nz(exp.get('phone'))}<br/>
    Email: {_nz(exp.get('email'))}
    """
    consignee_info = f"""
    <b>Buyer (Consignee, Overseas)</b><br/>
    {con['name']}<br/>{con['address']}<br/>
    Phone: {_nz(con.get('phone'))}<br/>
    Email: {_nz(con.get('email'))}
    """

    t_party = Table(
        [[Paragraph(exporter_info, normal), Paragraph(consignee_info, normal)]],
        colWidths=[8*cm, 8*cm],
    )
    t_party.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
    ]))
    story.extend([t_party, Spacer(1, 8)])

    # ---------- Invoice Details ----------
    story.append(Paragraph("<b>Invoice Details</b>", h2))

    invoice_date = data_summary.get("uk_invoice_date")
    currency = _nz(data_summary.get("currency"), "GBP")
    total_value = float(data_summary.get("total_value_gbp") or 0)
    total_qty = int(float(data_summary.get("total_quantity") or 0))
    carrier_name = CONFIG["carrier"]
    tracking_no = _nz(data_summary.get("tracking_no"), "N/A")

    tbl_details = [
        ["Invoice No.", invoice_no],
        ["Invoice Date", _nz(invoice_date)],
        ["Currency", currency],
        ["Total Value (GBP)", _fmt_gbp(total_value)],
        ["Total Quantity", f"{total_qty}"],
        ["Incoterms 2020", "DAP Hong Kong (default)"],
        ["Payment Terms", "100% Prepaid (Trade Payment)"],
        ["Reason for Export", "Commercial Export"],
        ["VAT Status", "Zero-rated export (0%), HMRC Notice 703"],
        ["Carrier", carrier_name],
        ["Tracking Reference", tracking_no],
    ]

    tbl = Table(tbl_details, colWidths=[5*cm, 10*cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([tbl, Spacer(1, 8)])

    # ---------- Itemized Goods ----------
    story.append(Paragraph("<b>Itemized Goods</b>", h2))

    item_rows = [["No.", "Product Code / SKU", "Description",
                  "Quantity", "Unit Price (GBP)", "Line Total (GBP)"]]

    grand_total, grand_qty = 0.0, 0
    line_no = 1
    for _, r in items.iterrows():
        q = int(r.get("quantity", 0) or 0)
        if q <= 0:
            continue

        tv = float(r.get("total_value", 0.0) or 0.0)
        uv = float(r.get("unit_value", 0.0) or 0.0)
        grand_qty += q
        grand_total += tv

        item_rows.append([
            str(line_no),
            str(r.get("skuid") or ""),
            Paragraph(str(r.get("product_description") or ""), desc_style),
            f"{q}",
            _fmt_gbp(uv),
            _fmt_gbp(tv),
        ])
        line_no += 1

    item_rows.append([
        "",
        "",
        Paragraph("<b>TOTALS</b>", desc_style),
        Paragraph(f"<b>{grand_qty}</b>", desc_style),
        "",
        Paragraph(f"<b>{_fmt_gbp(grand_total)}</b>", desc_style),
    ])

    goods_table = Table(
        item_rows,
        colWidths=[1.0*cm, 3.0*cm, 7.0*cm, 2.0*cm, 2.5*cm, 2.5*cm],
    )
    goods_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (5, -2), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
    ]))
    story.append(goods_table)

    # ---------- Footer / Declaration ----------
    story.extend([
        Spacer(1, 20),
        Paragraph(
            "<font size=8><i>This Commercial Invoice is issued by the UK exporter "
            "for zero-rated export supplies to the overseas related party. "
            "The export evidence (POE) and supplier purchase invoices are retained "
            "in the accounting records and can be provided to HMRC upon request.</i></font>",
            normal,
        ),
        Spacer(1, 20),
        Paragraph("Authorised Signature: _________________________________", normal),
        Spacer(1, 10),
        Paragraph("Name: Director, EMINZORA TRADE LTD", normal),
        Spacer(1, 10),
        Paragraph("Date: _______________________________________", normal),
    ])

    doc.build(story)
    print(f"[OK] Commercial Invoice generated: {pdf_path}")


if __name__ == "__main__":
    # 简单 CLI 用于单次测试：python export_ees_pdf.py GB-EMINZORA-251008-1
    if len(sys.argv) >= 2:
        inv = sys.argv[1]
        generate_export_evidence_pdf(inv)
        generate_commercial_invoice_pdf(inv)
