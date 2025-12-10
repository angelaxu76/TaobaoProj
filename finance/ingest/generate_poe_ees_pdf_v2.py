"""
Generate Export Evidence Summary (EES) PDF per POE.

This version follows the "best practice" discussed with the user:

- EES is a purely EXPLANATORY document.
- It does NOT list any unit prices or line values.
- It focuses on:
    * export facts (POE reference, MRN, date, carrier);
    * a summary list of shipped items (SKU + description + quantity only);
    * an explanation of discrepancies between POE and Commercial Invoice (CI);
    * a clear statement that such differences do not affect the validity of zero-rated export.

Public API (do NOT change):
    - generate_poe_ees_pdf(poe_id: str, output_dir: str) -> str

Internal helpers kept for backwards compatibility:
    - _nz
    - _fmt_gbp
    - _get_ees_sign_date
    - _prepare_items_for_ees (no longer used for prices, but retained)
    - fetch_poe_header
"""

import os
from pathlib import Path
import datetime as dt
from typing import Any, Dict, List

import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# 复用 CI 模块里的数据库连接、发票号生成逻辑和签名信息
from finance.ingest.generate_poe_invoice import (
    get_conn,
    _make_poe_invoice_no,
    SIGN_NAME,
    SIGN_TITLE,
    SIGN_IMAGE,
)


# ---------------------------------------------------------------------------
# Utility helpers (保留接口兼容)
# ---------------------------------------------------------------------------

def _nz(v: Any, fb: str = "N/A") -> str:
    """Return a human-friendly string for possibly-null values."""
    if v is None:
        return fb
    if isinstance(v, float) and pd.isna(v):
        return fb
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _fmt_gbp(v: Any) -> str:
    """
    Legacy helper for formatting GBP amounts.
    保留为了兼容，但当前 EES 不再打印任何金额。
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"£{float(v):,2f}"
    except Exception:
        return str(v)


def _get_ees_sign_date(poe_date: Any) -> str:
    """
    确定 EES 上的签署日期：
    - 若传入 poe_date，则使用该日期；
    - 否则使用今天。
    """
    if isinstance(poe_date, pd.Timestamp):
        poe_date = poe_date.date()
    if isinstance(poe_date, dt.date):
        return poe_date.strftime("%Y-%m-%d")
    return dt.date.today().strftime("%Y-%m-%d")


def _prepare_items_for_ees(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    兼容性保留的旧函数。

    以前会把带单价/金额的 DataFrame 转成 dict 列表。
    现在仅保留 SKU / 描述 / 数量。
    若外部还有地方调用它，不会报错，只是金额信息不再提供。
    """
    items: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return items

    for _, row in df.iterrows():
        qty = int(row.get("quantity") or 0)
        if qty <= 0:
            continue
        items.append(
            {
                "skuid": row.get("skuid"),
                "product_description": row.get("product_description"),
                "quantity": qty,
            }
        )
    return items


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------

def fetch_poe_header(poe_id: str) -> Dict[str, Any]:
    """
    从 export_shipments 读取某个 POE 的头信息。

    我们只需要少量字段：
      - poe_id
      - poe_mrn
      - poe_office
      - poe_date
      - carrier_name
      - tracking_no
      - poe_file (若存在)
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
        raise ValueError(f"export_shipments 中未找到 poe_id = {poe_id} 的记录。")
    row = df.iloc[0]
    return {
        "poe_id": row.get("poe_id"),
        "poe_mrn": row.get("poe_mrn"),
        "poe_office": row.get("poe_office"),
        "poe_date": row.get("poe_date"),
        "carrier_name": row.get("carrier_name"),
        "tracking_no": row.get("tracking_no"),
        "poe_file": row.get("poe_file"),
    }


def fetch_poe_items(poe_id: str) -> pd.DataFrame:
    """
    读取某个 POE 下的所有商品行（按 SKU），不区分是否有采购成本。

    对 EES 来说这是正确行为：
      - EES 必须反映实际出口事实（与 POE 对齐）；
      - 不能因为没有采购成本就丢掉 HK 旧库存等商品。

    字段：
      - skuid
      - product_description
      - quantity
    """
    sql = """
        SELECT
            skuid,
            product_description,
            quantity
        FROM public.export_shipments
        WHERE poe_id = %s
          AND skuid IS NOT NULL
          AND skuid <> ''
        ORDER BY skuid;
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=(poe_id,))
    if df.empty:
        raise ValueError(f"poe_id = {poe_id} 未找到任何带 SKU 的商品行，无法生成 EES。")
    df["quantity"] = df["quantity"].fillna(0).astype(int)
    return df


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_poe_ees_pdf(poe_id: str, output_dir: str) -> str:
    """
    为给定 POE 生成一份 Export Evidence Summary (EES) PDF。

    Public API:
        generate_poe_ees_pdf(poe_id: str, output_dir: str) -> str (pdf_path)

    特点：
    - 不显示任何价格或金额；
    - 仅列出 SKU / 描述 / 数量；
    - 提供一段解释性文字，说明 CI 与 POE 的差异；
    - 作为 CI 与 POE 之间的“逻辑连接说明书”。
    """
    # 确保输出目录存在
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 注册支持中文的字体（若失败则回退到 Helvetica）
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        base_font_name = "HeiseiKakuGo-W5"
    except Exception:
        base_font_name = "Helvetica"

    # 读取 POE 头信息 + 商品行
    header = fetch_poe_header(poe_id)
    poe_mrn = header.get("poe_mrn")
    poe_office = header.get("poe_office")
    poe_date = header.get("poe_date")
    carrier_name = header.get("carrier_name")
    # 默认承运人：如果数据库为空，就用 ECMS
    if not carrier_name or str(carrier_name).strip() == "":
        carrier_name = "ECMS"
    tracking_no = header.get("tracking_no")  # 不再打印出来，只是保留变量

    items_df = fetch_poe_items(poe_id)
    total_qty = int(items_df["quantity"].sum())

    # 从 POE 推导对应的 Commercial Invoice 号（需要 poe_date）
    invoice_no = _make_poe_invoice_no(poe_id, poe_date)
    sign_date_str = _get_ees_sign_date(poe_date)

    # ------------------------------------------------------------------
    # Build PDF
    # ------------------------------------------------------------------
    pdf_path = out_dir / f"EES_{poe_id}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = base_font_name
    normal.fontSize = 9
    normal.leading = 12

    h1 = ParagraphStyle(
        "Heading1",
        parent=styles["Heading1"],
        fontName=base_font_name,
        fontSize=14,
        leading=18,
        spaceAfter=12,
        alignment=1,  # center
    )
    h2 = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontName=base_font_name,
        fontSize=11,
        leading=14,
        spaceAfter=8,
    )
    desc_style = ParagraphStyle(
        "Desc",
        parent=normal,
        fontSize=8,
        leading=10,
    )

    story: List[Any] = []

    # ---------- Title ----------
    story.append(Paragraph("Export Evidence Summary (EES)", h1))
    story.append(Spacer(1, 6))

    # ---------- Header Meta ----------
    # 注意：这里已移除 Tracking Number 行
    meta_rows = [
        ["POE / Shipment Reference", _nz(poe_id)],
        ["Related Commercial Invoice", _nz(invoice_no)],
        ["MRN / Customs Reference", _nz(poe_mrn)],
        ["Customs Office", _nz(poe_office)],
        ["Export Date", _nz(poe_date)],
        ["Carrier", _nz(carrier_name)],
        ["Total Shipped Quantity", str(total_qty)],
    ]
    t_meta = Table(meta_rows, colWidths=[5 * cm, 11 * cm])
    t_meta.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONT", (0, 0), (-1, -1), base_font_name, 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ]
        )
    )
    story.extend([t_meta, Spacer(1, 12)])

    # ---------- 1. Statement of Export ----------
    story.append(Paragraph("<b>1. Statement of Export</b>", h2))
    p_export = Paragraph(
        """
        This document is issued to confirm that the goods associated with the above
        Commercial Invoice and POE / shipment reference have physically left the
        United Kingdom. The export has been processed via the relevant customs
        procedures and is intended to qualify for UK VAT zero-rating in accordance
        with HMRC Notice 703 (Exports and removals of goods from the UK).
        """,
        normal,
    )
    story.extend([p_export, Spacer(1, 8)])

    # ---------- 2. Explanation of Document Discrepancies ----------
    story.append(Paragraph("<b>2. Explanation of Document Discrepancies</b>", h2))
    p_diff = Paragraph(
        """
        Differences between the Commercial Invoice (CI) and the Proof of Export (POE)
        are expected and arise from the consolidated cross-border fulfilment model
        used in this supply chain. These differences are governed by the UK–HK
        Cross-Border Trade Agreement (the “Agreement”), in particular Clauses
        <b>1A</b> and <b>5 / 5A</b>:
        
        <br/><br/>
        <b>1. Consignee Difference</b><br/>
        The POE may show a platform-related entity (such as Alipay.com Co., Ltd.)
        as consignee or declarant. This reflects the platform’s role as authorised
        agent for customs and logistics purposes and does <u>not</u> alter the
        underlying buyer–seller relationship between EMINZORA TRADE LTD (Seller)
        and HONG KONG ANGEL XUAN TRADING CO., LIMITED (Buyer).
        
        <br/><br/>
        <b>2. Declared Value Difference</b><br/>
        The POE declared value is determined by the platform in line with its
        retail and customs processes and is used for statistical and import / export
        compliance purposes. The CI value represents the agreed B2B wholesale
        transfer price between the parties. As stated in Clauses 5 / 5A of the
        Agreement, these two values serve different regulatory purposes and are not
        expected to match exactly.
        
        <br/><br/>
        <b>3. Quantity Difference (Consolidated Shipment)</b><br/>
        The total quantity of goods shown on the POE may exceed the quantity listed
        on the related CI. This occurs because the Buyer consolidates multiple
        inventory sources into a single export shipment for logistical efficiency.
        
        <br/><br/>
        Specifically, the POE may include:<br/>
        &bull; Goods sold by the Seller (UK) to the Buyer (HK) under the B2B
          agreement in force at the time of shipment, as itemised on the CI; and<br/>
        &bull; Goods already owned by the Buyer prior to the shipment date
          (including pre-existing UK inventory), which were not part of this B2B
          sale but were exported together in the same consignment.
        
        <br/><br/>
        Accordingly:<br/>
        &bull; The POE and this EES evidence the complete physical export of all
          items in the shipment, regardless of their commercial origin; and<br/>
        &bull; The CI reflects only the B2B transaction value and quantity relevant
          for VAT and settlement purposes.
        
        <br/><br/>
        These differences are an inherent and legitimate feature of the agreed
        fulfilment and export model and do <u>not</u> affect the validity of the
        UK–HK B2B sale nor the eligibility of this export for VAT zero-rating,
        provided that the physical export of goods can be evidenced by the POE / MRN
        and associated transport records.
        """,
        normal,
    )
    story.extend([p_diff, Spacer(1, 12)])

    # ---------- 3. Shipped Items (Summary, no prices) ----------
    story.append(Paragraph("<b>3. Shipped Items (Summary)</b>", h2))

    item_rows: List[List[Any]] = [["Product Code / SKU", "Goods Description", "Quantity"]]
    for _, r in items_df.iterrows():
        qty = int(r.get("quantity") or 0)
        if qty <= 0:
            continue

        item_rows.append(
            [
                _nz(r.get("skuid"), ""),
                Paragraph(_nz(r.get("product_description"), ""), desc_style),
                str(qty),
            ]
        )

    items_table = Table(
        item_rows,
        colWidths=[3.0 * cm, 9.0 * cm, 2.0 * cm],
        repeatRows=1,
    )
    items_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONT", (0, 0), (-1, -1), base_font_name, 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
            ]
        )
    )
    story.extend([items_table, Spacer(1, 12)])

    # ---------- 4. Conclusion & Signature ----------
    story.append(Paragraph("<b>4. Conclusion</b>", h2))
    p_conclusion = Paragraph(
        """
        Based on the above, the Seller confirms that:
        <br/><br/>
        (a) The goods listed in this Export Evidence Summary and in the associated
            POE have been shipped from the United Kingdom; and
        <br/>
        (b) The differences between the Commercial Invoice and the POE are the
            natural result of the agreed cross-border fulfilment model and do not
            undermine the validity of the underlying B2B sale nor the application
            of VAT zero-rating for this export.
        """,
        normal,
    )
    story.extend([p_conclusion, Spacer(1, 12)])

    # ---- 签名区（带电子签名 + 职位） ----
    story.append(Paragraph("<b>Authorised Signature (UK)</b>", h2))
    story.append(Spacer(1, 4))

    # 电子签名图片（如果存在）
    if SIGN_IMAGE and os.path.exists(SIGN_IMAGE):
        sig_img = Image(SIGN_IMAGE)
        # 限制最大宽度和高度，但保持原始宽高比，不会被拉伸变形
        sig_img._restrictSize(5 * cm, 2.5 * cm)
        story.append(sig_img)
        story.append(Spacer(1, 4))

    # Name / Title / Date
    story.append(Paragraph(f"Name: {SIGN_NAME}", normal))
    story.append(Paragraph(f"Title: {SIGN_TITLE}", normal))
    story.append(Paragraph(f"Date: {sign_date_str}", normal))

    # 生成 PDF
    doc.build(story)

    return str(pdf_path)


if __name__ == "__main__":
    # 简单命令行测试入口（可选）
    import argparse

    parser = argparse.ArgumentParser(description="Generate Export Evidence Summary (EES) PDF for a POE.")
    parser.add_argument("--poe-id", required=True, help="POE / Shipment reference ID, e.g. SD10009905718779")
    parser.add_argument(
        "--output-dir",
        required=False,
        default=".",
        help="Directory to store the generated EES PDF.",
    )
    args = parser.parse_args()

    out_file = generate_poe_ees_pdf(args.poe_id, args.output_dir)
    print("[OK] Generated EES PDF:", out_file)
