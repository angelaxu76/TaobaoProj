"""
Generate Export Evidence Summary PDF
Compliant with HMRC Notice 703 (Zero-rated Export)
Author: EMINZORA Compliance Automation
"""

import os, sys, re, datetime as dt
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
    "output_dir": r"D:\OneDrive\CrossBorderDocs\06_Export_Proofs",
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
    t = re.sub(r"\blook\s+step\b", "", t, flags=re.I)        # marketing 词
    t = re.sub(r"\bk\s*-\b", "", t, flags=re.I)               # “k -” 残片
    t = re.sub(r"\byards?\s*\d+\b", "", t, flags=re.I)        # “yards 39”
    t = re.sub(r"\bsize\s*\d+\b", "", t, flags=re.I)
    t = re.sub(r"\b\d+(\.\d+)?\s*cm\b", "", t, flags=re.I)
    t = re.sub(r"\bcm\b", "", t, flags=re.I)
    t = re.sub(r"\bchnx\b", "", t, flags=re.I)                # 可能的抓取残片

    # 统一性别/品类词序，消除冲突组合
    t = re.sub(r"\bmen['’]s\s+shoes\s+men['’]s\s+boots\b", "men's boots", t, flags=re.I)
    t = re.sub(r"\bwomen['’]s\s+shoes\s+men['’]s\s+boots\b", "women's boots", t, flags=re.I)

    # 多余空白压缩
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def _prepare_items(df):
    if df.empty:
        return df
    df = df.fillna({"quantity": 0, "value_gbp": 0})
    df["product_description"] = df["product_description"].astype(str).apply(_clean_desc)
    g = df.groupby(["skuid", "product_description"], as_index=False).agg(
        quantity=("quantity", "sum"),
        total_value=("value_gbp", "sum"),
    )
    g["unit_value"] = (g["total_value"] / g["quantity"].replace(0, pd.NA)).fillna(0.0).round(2)
    g = g.sort_values(by=["product_description", "skuid"])
    return g

# ---------- DB ----------
def fetch_export_summary(invoice_no: str):
    conn = psycopg2.connect(**CONFIG["db"])
    sql = "SELECT * FROM public.export_shipments_summary WHERE uk_invoice_no = %s LIMIT 1;"
    df = pd.read_sql(sql, conn, params=[invoice_no])
    conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

def fetch_itemized_goods(invoice_no: str):
    conn = psycopg2.connect(**CONFIG["db"])
    sql = "SELECT skuid, product_description, quantity, value_gbp FROM public.export_shipments WHERE uk_invoice_no = %s;"
    df = pd.read_sql(sql, conn, params=[invoice_no])
    conn.close()
    if "value_gbp" in df.columns:
        df["total_value"] = df["value_gbp"]
    return df

# ---------- PDF ----------
def generate_export_evidence_pdf(invoice_no: str):
    data_summary = fetch_export_summary(invoice_no)
    if not data_summary:
        print(f"[WARN] Invoice {invoice_no} not found.")
        return

    items = fetch_itemized_goods(invoice_no)
    items = _prepare_items(items)

    out_dir = os.path.join(CONFIG["output_dir"], data_summary["folder_name"])
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"ExportEvidenceSummary_{invoice_no}.pdf")

    # 样式
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=1.8*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title_style = ParagraphStyle("title", parent=normal, fontSize=16, leading=20, alignment=1, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=normal, fontSize=12, leading=15, spaceBefore=8, spaceAfter=6)
    desc_style = ParagraphStyle("desc", fontName="HeiseiKakuGo-W5", fontSize=8, leading=10, wordWrap="CJK")

    text = []

    # ---------- Title ----------
    text.append(Paragraph("<b>Export Evidence Summary (VAT Zero-Rated Export)</b><br/><font size=9>(Compliant with HMRC Notice 703)</font>", title_style))

    # ---------- Exporter & Consignee ----------
    exp, con = CONFIG["exporter"], CONFIG["consignee"]
    def _nz(v, fb="N/A"):
        s = str(v or "").strip()
        return s or fb

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

    t = Table([[Paragraph(exporter_info, normal), Paragraph(consignee_info, normal)]], colWidths=[8*cm, 8*cm])
    text.extend([t, Spacer(1, 8)])

    # ---------- Shipment & Invoice Details ----------
    text.append(Paragraph("<b>Shipment & Invoice Details</b>", h2))


    tbl_data = [
        ["Internal Reference No.", invoice_no],
        ["Date", _nz(data_summary.get("uk_invoice_date"))],
        ["Currency", _nz(data_summary.get("currency"), "GBP")],
        ["Total Value (GBP)", f"{float(data_summary.get('total_value_gbp') or 0):,.2f}"],
        ["Total Quantity", f"{int(float(data_summary.get('total_quantity') or 0))}"],
        ["Total Gross Weight (kg)", _nz(data_summary.get("total_gross_weight_kg"))],
        ["Carrier", CONFIG["carrier"]],
        ["Export Route", CONFIG["route"]],
        ["Tracking Reference", _nz(data_summary.get("tracking_no"), "N/A")],
    ]




    tbl = Table(tbl_data, colWidths=[5*cm, 10*cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,-1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    text.extend([tbl, Spacer(1, 8)])

    # ---------- Itemized Goods List ----------
    text.append(Paragraph("<b>Itemized Goods List (Summary)</b>", h2))

    item_rows = [["Product Code / SKU", "Goods Description", "Quantity", "Unit Value (GBP)", "Total Value (GBP)"]]
    total_val, total_qty = 0.0, 0

    for _, r in items.iterrows():
        # 跳过空 SKU 或数量为 0 的行
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
            f"{q}", f"{uv:,.2f}", f"{tv:,.2f}"
        ])

    # ✅ 合计行修正：右对齐、单元格不再出现 <b> 标签串
    item_rows.append(["", Paragraph("<b>TOTALS</b>", desc_style),
                    Paragraph(f"<b>{total_qty}</b>", desc_style), "", 
                    Paragraph(f"<b>{total_val:,.2f}</b>", desc_style)])

    goods_table = Table(item_rows, colWidths=[3.2*cm, 7.4*cm, 2.1*cm, 2.6*cm, 2.8*cm])
    goods_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,-1), "HeiseiKakuGo-W5", 8),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (2,1), (-1,-2), "CENTER"),
        ("ALIGN", (3,1), (4,-2), "RIGHT"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),
    ]))
    text.extend([
        goods_table,
        Paragraph("<font size=8><i>Note: Summary derived from underlying UK supplier invoices retained on file.</i></font>", normal),
        Spacer(1, 10)
    ])




    # ---------- Proof of Export ----------
    # ---------- Proof of Export ----------
    text.append(Paragraph("<b>Proof of Export (POE)</b>", h2))

    attachments_text = (
        f"1. POE_{data_summary.get('poe_date','')}.pdf<br/>"
        f"2. Internal_Reference_{invoice_no}.pdf<br/>"
    )

    poe_tbl = [
        ["POE ID", _nz(data_summary.get("poe_id"))],
        ["MRN", _nz(data_summary.get("poe_mrn"))],
        ["Office of Exit", _nz(data_summary.get("poe_office"))],
        ["Date of Export", _nz(data_summary.get("poe_date"))],
        ["Evidence Type", "POE PDF + Internal Reference Summary"],  # ✅ 改为你实际存在的文件组合
        ["Attachments", Paragraph(
            f"1. POE_{data_summary.get('poe_date','')}.pdf<br/>"
            f"2. Internal_Reference_{invoice_no}.pdf",
            desc_style
        )],
    ]

    poe_table = Table(poe_tbl, colWidths=[5*cm, 10*cm])
    poe_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,-1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    text.extend([poe_table, Spacer(1, 12)])


    # ---------- Declaration ----------
    # ---------- Declaration ----------
    text.append(Paragraph("<b>Declaration</b>", h2))
    text.append(Paragraph(CONFIG["declaration"], normal))

    # ✅ 扩大签名区留白
    text.extend([
        Spacer(1, 30),  # 原来是 20，可改 30~60
        Paragraph("Prepared by: _________________________________", normal),
        Spacer(1, 10),
        Paragraph("Position: Director, EMINZORA TRADE LTD", normal),
        Spacer(1, 10),
        Paragraph("Date: _______________________________________", normal),
        Spacer(1, 10),
        Paragraph("Signature: __________________________________", normal),
        Spacer(1, 40),  # 尾部再加一段额外空白
    ])


    doc.build(text)
    print(f"[OK] Export Evidence Summary generated: {pdf_path}")


def generate_commercial_invoice_pdf(invoice_no: str):
    """
    Generate Commercial Invoice (CI) PDF for a given internal invoice_no.
    CI = 英国出口给香港的商业发票，金额与 EES / POE 一致。
    """
    data_summary = fetch_export_summary(invoice_no)
    if not data_summary:
        print(f"[WARN] Invoice {invoice_no} not found in export_shipments_summary.")
        return

    items = fetch_itemized_goods(invoice_no)
    items = _prepare_items(items)  # 已经按 skuid + 描述聚合，并算好 unit_value / total_value

    # 输出目录与 EES 保持一致：D:\OneDrive\CrossBorderDocs\06_Export_Proofs\{folder_name}
    folder_name = data_summary.get("folder_name") or "UNKNOWN"
    out_dir = os.path.join(CONFIG["output_dir"], folder_name)
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"CommercialInvoice_{invoice_no}.pdf")

    # ========= reportlab 文档基础 =========
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=1.8*cm, bottomMargin=1.5*cm
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title_style = ParagraphStyle(
        "title", parent=normal,
        fontSize=16, leading=20,
        alignment=1,  # center
        spaceAfter=10
    )
    h2 = ParagraphStyle(
        "h2", parent=normal,
        fontSize=12, leading=15,
        spaceBefore=8, spaceAfter=6
    )
    desc_style = ParagraphStyle(
        "desc",
        fontName="HeiseiKakuGo-W5",
        fontSize=8, leading=10,
        wordWrap="CJK"
    )

    def _nz(v, fb="N/A"):
        s = str(v or "").strip()
        return s or fb

    exp, con = CONFIG["exporter"], CONFIG["consignee"]

    story = []

    # ---------- Title ----------
    story.append(Paragraph("<b>COMMERCIAL INVOICE</b>", title_style))

    # ---------- Exporter & Consignee ----------
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
    <b>Buyer / Consignee (Hong Kong)</b><br/>
    {con['name']}<br/>{con['address']}<br/>
    Phone: {_nz(con.get('phone'))}<br/>
    Email: {_nz(con.get('email'))}
    """

    t_party = Table(
        [[Paragraph(exporter_info, normal), Paragraph(consignee_info, normal)]],
        colWidths=[8*cm, 8*cm]
    )
    story.extend([t_party, Spacer(1, 8)])

    # ---------- Invoice Details ----------
    story.append(Paragraph("<b>Invoice Details</b>", h2))

    invoice_date = data_summary.get("uk_invoice_date")
    currency = _nz(data_summary.get("currency"), "GBP")
    total_value = float(data_summary.get("total_value_gbp") or 0)
    total_qty = int(float(data_summary.get("total_quantity") or 0))
    carrier_name = _nz(data_summary.get("carrier_name"), CONFIG["carrier"])
    tracking_no = _nz(data_summary.get("tracking_no"), "N/A")

    tbl_details = [
        ["Invoice No.", invoice_no],
        ["Invoice Date", _nz(invoice_date)],
        ["Currency", currency],
        ["Total Value (GBP)", f"{total_value:,.2f}"],
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
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,-1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.extend([tbl, Spacer(1, 8)])

    # ---------- Itemized Goods (Invoice Lines) ----------
    story.append(Paragraph("<b>Itemized Goods</b>", h2))

    item_rows = [["No.", "Product Code / SKU", "Description", "Quantity", "Unit Price (GBP)", "Line Total (GBP)"]]

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
            f"{uv:,.2f}",
            f"{tv:,.2f}",
        ])
        line_no += 1

    # Totals row
    item_rows.append([
        "",
        "",
        Paragraph("<b>TOTALS</b>", desc_style),
        Paragraph(f"<b>{grand_qty}</b>", desc_style),
        "",
        Paragraph(f"<b>{grand_total:,.2f}</b>", desc_style),
    ])

    goods_table = Table(
        item_rows,
        colWidths=[1.0*cm, 3.0*cm, 7.0*cm, 2.0*cm, 2.5*cm, 2.5*cm]
    )
    goods_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,-1), "HeiseiKakuGo-W5", 8),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (0,1), (0,-1), "CENTER"),
        ("ALIGN", (3,1), (5,-2), "RIGHT"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),
    ]))
    story.extend([goods_table, Spacer(1, 10)])

    # ---------- Declaration ----------
    story.append(Paragraph("<b>Declaration by Exporter</b>", h2))
    declaration_text = (
        "I hereby certify that the information on this Commercial Invoice is true and correct, "
        "that the goods described herein are intended for export from the United Kingdom, "
        "and that this supply is treated as zero-rated for VAT purposes under HMRC Notice 703. "
        "All supporting documents (including UK supplier invoices, packing lists, freight "
        "documents, and proof of export) are retained on file for the statutory period."
    )
    story.append(Paragraph(declaration_text, normal))

    story.extend([
        Spacer(1, 30),
        Paragraph("Exporter: EMINZORA TRADE LTD", normal),
        Spacer(1, 8),
        Paragraph("Name: _________________________________", normal),
        Spacer(1, 8),
        Paragraph("Title: Director", normal),
        Spacer(1, 8),
        Paragraph("Signature: ____________________________", normal),
        Spacer(1, 8),
        Paragraph("Date: _________________________________", normal),
        Spacer(1, 30),
    ])

    doc.build(story)
    print(f"[OK] Commercial Invoice generated: {pdf_path}")

# ---------- CLI ----------
if __name__ == "__main__":
    invoice_no = input("Enter invoice no [default: GB-EMINZORA-251031-1]: ").strip() or "GB-EMINZORA-251031-1"
    generate_export_evidence_pdf(invoice_no)
