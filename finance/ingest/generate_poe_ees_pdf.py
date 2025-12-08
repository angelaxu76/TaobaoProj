"""
Generate Export Evidence Summary PDF per POE
- One POE -> One EES PDF
- Amounts fully aligned with CommercialInvoice_PoE (using build_cost_and_price)
- Compliant with HMRC Notice 703 (Zero-rated Export)

Save as: finance/ingest/generate_poe_ees_pdf.py
"""

import os
from pathlib import Path
import datetime as dt

import psycopg2
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ------- 项目内配置 -------
from config import PGSQL_CONFIG
from finance_config import FINANCE_EES

# 复用发票模块的逻辑，确保金额完全一致
from finance.ingest.generate_poe_invoice import (
    get_conn,
    load_poe_lines,
    build_cost_and_price,
    _make_poe_invoice_no,
)

# ------- 字体：用于中/英混排 -------
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

# ------- 签名配置（与发票保持一致） -------
SIGN_NAME = "XIAODAN MA"
SIGN_TITLE = "Director, EMINZORA TRADE LTD"
SIGN_IMAGE = r"D:\OneDrive\CrossBorderDocs_UK\00_Templates\signatures\xiaodan_ma_signature.png"


# ----------------- 小工具函数 -----------------
def _nz(v, fb="N/A"):
    """空值/None -> 备用字符串"""
    s = str(v or "").strip()
    return s or fb


def _fmt_gbp(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return "0.00"


def _get_ees_sign_date(poe_date: dt.date | None) -> dt.date:
    """
    EES 签字日期：默认为 POE 日期 + 3 天；
    如果拿不到 POE 日期，就用今天。
    """
    if isinstance(poe_date, dt.datetime):
        poe_date = poe_date.date()
    if isinstance(poe_date, dt.date):
        return poe_date + dt.timedelta(days=3)
    return dt.date.today()


def _prepare_items_for_ees(df: pd.DataFrame) -> pd.DataFrame:
    """
    基于 build_cost_and_price() 的结果，生成 EES 明细：
    - 使用 line_price_gbp 作为总金额
    - 按 (skuid, product_description) 聚合
    - 计算 unit_value = total_value / quantity
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "skuid", "product_description",
            "quantity", "unit_value", "total_value"
        ])

    df = df.copy()

    # skuid 统一成字符串
    if "skuid" in df.columns:
        df["skuid"] = df["skuid"].astype(str).str.strip()
    else:
        df["skuid"] = ""

    # 确保有 product_description 列，并填空值
    if "product_description" not in df.columns:
        df["product_description"] = ""
    df["product_description"] = df["product_description"].fillna("").astype(str)

    # 数量
    df["quantity"] = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0).astype(int)

    # 行金额（和发票用的是同一列）
    df["line_price_gbp"] = pd.to_numeric(
        df.get("line_price_gbp", 0.0),
        errors="coerce"
    ).fillna(0.0).astype(float)

    # 分组聚合
    grouped = (
        df.groupby(["skuid", "product_description"], dropna=False)[
            ["quantity", "line_price_gbp"]
        ]
        .sum()
        .reset_index()
    )

    # 单价 = 总价 / 数量
    grouped["unit_value"] = (
        grouped["line_price_gbp"]
        / grouped["quantity"].replace(0, pd.NA)
    ).fillna(0.0).round(2)

    grouped.rename(columns={"line_price_gbp": "total_value"}, inplace=True)

    return grouped[["skuid", "product_description", "quantity", "unit_value", "total_value"]]



def fetch_poe_header(poe_id: str) -> dict:
    """
    从 export_shipments 中取 POE 头信息（取第一行即可）：
    - poe_id, poe_mrn, poe_office, poe_date, carrier_name, tracking_no, poe_file（如有）
    """
    sql = """
        SELECT
            poe_id,
            poe_mrn,
            poe_office,
            poe_date,
            carrier_name,
            tracking_no,
            poe_file
        FROM public.export_shipments
        WHERE poe_id = %s
        ORDER BY id
        LIMIT 1;
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=(poe_id,))
    if df.empty:
        raise ValueError(f"export_shipments 中没有找到 poe_id = {poe_id} 的头记录。")
    return df.iloc[0].to_dict()


# ----------------- 核心函数：生成单个 POE 的 EES PDF -----------------
def generate_poe_ees_pdf(poe_id: str, output_dir: str) -> str:
    """
    按单个 POE 生成 Export Evidence Summary PDF：

    - 输入:
        poe_id:      比如 "SD10009905718779"
        output_dir:  比如 r"D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs\20251022"

    - 输出:
        返回生成的 EES PDF 路径
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 读取 POE 明细 + 成本&售价（与发票完全一致）
    df_raw = load_poe_lines(poe_id)
    df_cost = build_cost_and_price(df_raw)

    # 2) 汇总金额/数量（用于抬头 & 合计）
    total_value = df_cost["line_price_gbp"].sum().round(2)
    total_qty = int(df_cost["quantity"].sum())

    # 3) 生成 EES 用的商品表
    items = _prepare_items_for_ees(df_cost)

    # 4) 读取 POE 头信息
    header = fetch_poe_header(poe_id)
    poe_mrn = header.get("poe_mrn")
    poe_office = header.get("poe_office")
    poe_date = header.get("poe_date")
    if isinstance(poe_date, pd.Timestamp):
        poe_date = poe_date.date()

    carrier_name = header.get("carrier_name") or ""
    tracking_no = header.get("tracking_no") or ""
    poe_file = header.get("poe_file") or f"POE_{poe_id}.pdf"

    # 5) 生成对应的 CI-POE 发票号（与 generate_poe_invoice.py 保持一致）
    invoice_no = _make_poe_invoice_no(poe_id, poe_date)

    # 6) EES 签字日期
    ees_sign_date = _get_ees_sign_date(poe_date)
    ees_sign_date_str = ees_sign_date.isoformat()

    # 7) Exporter / Consignee & 声明文本
    exporter = FINANCE_EES["exporter"]
    consignee = FINANCE_EES["consignee"]
    declaration_text = FINANCE_EES["declaration"]

    # 8) 准备 PDF
    pdf_path = out_dir / f"ExportEvidenceSummary_{poe_id}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title_style = ParagraphStyle(
        "title",
        parent=normal,
        fontSize=16,
        leading=20,
        alignment=1,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=normal,
        fontSize=12,
        leading=15,
        spaceBefore=8,
        spaceAfter=6,
    )
    desc_style = ParagraphStyle(
        "desc",
        fontName="HeiseiKakuGo-W5",
        fontSize=8,
        leading=10,
        wordWrap="CJK",
    )

    story = []

    # ---------- 标题 ----------
    story.append(Paragraph(
        "<b>Export Evidence Summary (VAT Zero-Rated Export)</b>"
        "<br/><font size=9>(Compliant with HMRC Notice 703)</font>",
        title_style,
    ))

    # ---------- Exporter & Consignee ----------
    exporter_info = f"""
    <b>Exporter (UK)</b><br/>
    {exporter['name']}<br/>{exporter['address']}<br/>
    Company No.: {_nz(exporter.get('company_no'))}<br/>
    VAT No.: {_nz(exporter.get('vat_no'))}<br/>
    EORI: {_nz(exporter.get('eori_no'))}<br/>
    Phone: {_nz(exporter.get('phone'))}<br/>
    Email: {_nz(exporter.get('email'))}
    """

    consignee_info = f"""
    <b>Consignee (Overseas Entity)</b><br/>
    {consignee['name']}<br/>{consignee['address']}<br/>
    Phone: {_nz(consignee.get('phone'))}<br/>
    Email: {_nz(consignee.get('email'))}<br/>
    Jurisdiction: Hong Kong SAR
    """

    t_party = Table(
        [[Paragraph(exporter_info, normal), Paragraph(consignee_info, normal)]],
        colWidths=[8 * cm, 8 * cm],
    )
    t_party.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
    ]))
    story.extend([t_party, Spacer(1, 8)])

    # ---------- Shipment & Invoice Details ----------
    story.append(Paragraph("<b>Shipment & Invoice Details</b>", h2))

    tbl_details = [
        ["Related Commercial Invoice", invoice_no],
        ["Invoice Currency", "GBP"],
        ["Invoice Total Value (GBP)", _fmt_gbp(total_value)],
        ["Total Quantity (Units)", str(total_qty)],
        ["Delivery Terms", "FCA (ECMS UK warehouse), Incoterms® 2020"],
        ["Carrier", _nz(carrier_name)],
        ["Tracking Reference", _nz(tracking_no, "N/A")],
    ]

    tbl = Table(tbl_details, colWidths=[5 * cm, 10 * cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([tbl, Spacer(1, 8)])

    # ---------- Itemized Goods List ----------
    story.append(Paragraph("<b>Itemized Goods List (Summary)</b>", h2))

    item_rows = [["Product Code / SKU", "Goods Description",
                  "Quantity", "Unit Value (GBP)", "Total Value (GBP)"]]

    total_val_acc, total_qty_acc = 0.0, 0
    for _, r in items.iterrows():
        q = int(r.get("quantity", 0) or 0)
        if q <= 0:
            continue

        tv = float(r.get("total_value", 0.0) or 0.0)
        uv = float(r.get("unit_value", 0.0) or 0.0)
        total_qty_acc += q
        total_val_acc += tv

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
        Paragraph(f"<b>{total_qty_acc}</b>", desc_style),
        "",
        Paragraph(f"<b>{_fmt_gbp(total_val_acc)}</b>", desc_style),
    ])

    goods_table = Table(
        item_rows,
        colWidths=[3.0 * cm, 7.5 * cm, 2.0 * cm, 2.6 * cm, 2.9 * cm],
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
            "are retained separately in the accounting records and can be provided "
            "to HMRC upon request.</i></font>",
            normal,
        ),
        Spacer(1, 10),
    ])

    # ---------- Proof of Export ----------
    story.append(Paragraph("<b>Proof of Export (POE)</b>", h2))

    poe_tbl = [
        ["POE ID", _nz(poe_id)],
        ["MRN / Customs Reference", _nz(poe_mrn)],
        ["Office of Exit", _nz(poe_office)],
        ["Date of Export", _nz(poe_date)],
        ["Evidence Type", "POE (UK customs export declaration PDF)"],
        [
            "Attachments",
            Paragraph(f"1. {poe_file}", desc_style),
        ],
    ]

    poe_table = Table(poe_tbl, colWidths=[5 * cm, 10 * cm])
    poe_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONT", (0, 0), (-1, -1), "HeiseiKakuGo-W5", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([poe_table, Spacer(1, 12)])

    # ---------- Platform Fulfilment Note ----------
    platform_note = Paragraph(
        """
        <b>Platform Fulfilment Note:</b><br/>
        This shipment is executed under the Alibaba/Cainiao cross-border fulfilment model.
        The Proof of Export (POE) may list <i>Alipay.com Co., Ltd.</i> as the Consignee for
        customs declaration purposes, reflecting the platform’s role as the authorised
        declarant and logistics provider. This administrative designation does <u>not</u> alter
        the commercial buyer–seller relationship between EMINZORA TRADE LTD (Seller)
        and HONG KONG ANGEL XUAN TRADING CO., LIMITED (Buyer), as established in
        the UK–HK Cross-Border Trade Agreement (v4.2).
        """,
        normal,
    )
    story.extend([platform_note, Spacer(1, 8)])

    # ---------- 价差/四舍五入说明（可选） ----------
    rounding_note = Paragraph(
        "<font size=8><i>Note: The statistical value shown on the customs POE may "
        "differ from the Commercial Invoice value due to platform pricing or rounding. "
        "For VAT zero-rating purposes, the Commercial Invoice value prevails, supported "
        "by this Export Evidence Summary and the underlying POE.</i></font>",
        normal,
    )
    story.extend([rounding_note, Spacer(1, 8)])

    # ---------- Declaration ----------
    story.append(Paragraph("<b>Declaration</b>", h2))
    story.append(Paragraph(declaration_text, normal))

    story.append(Paragraph(
        "The Seller confirms that the goods listed in this summary have been physically "
        "exported from the UK within the required time limit and that all supporting "
        "documents will be retained for HMRC audit purposes.",
        normal,
    ))

    # ---------- 签名区 ----------
    sig_block = [
        Spacer(1, 30),
        Paragraph(f"Prepared by: {SIGN_NAME}", normal),
        Spacer(1, 10),
        Paragraph(f"Position: {SIGN_TITLE}", normal),
        Spacer(1, 10),
        Paragraph("Signature:", normal),
    ]

    if SIGN_IMAGE and os.path.exists(SIGN_IMAGE):
        sig_block.append(Spacer(1, 4))
        sig_block.append(Image(SIGN_IMAGE, width=4 * cm, height=2 * cm))
    else:
        sig_block.append(Spacer(1, 4))
        sig_block.append(Paragraph("__________________________________", normal))

    sig_block.extend([
        Spacer(1, 10),
        Paragraph(f"Date: {ees_sign_date_str}", normal),
        Spacer(1, 30),
    ])

    story.extend(sig_block)

    # ---------- 生成 PDF ----------
    doc.build(story)
    print(f"[OK] Export Evidence Summary generated: {pdf_path}")
    return str(pdf_path)


# ----------------- CLI 用法 -----------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python generate_poe_ees_pdf.py <poe_id> <output_dir>")
        print("Example:")
        print(r"  python generate_poe_ees_pdf.py SD10009905718779 D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs\20251022")
        sys.exit(1)

    poe_id_arg = sys.argv[1]
    output_dir_arg = sys.argv[2]

    pdf_p = generate_poe_ees_pdf(poe_id_arg, output_dir_arg)
    print(f"[DONE] EES PDF : {pdf_p}")
