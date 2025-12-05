import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

# finance_config.py 与本文件在同一目录
from finance_config import FINANCE_EES


# 不向香港公司收费的类别（可按需调整）
EXCLUDE_CATEGORIES = {
    "Personal expenses",
    "Sales",
    "Non-taxable income",
    "Client entertainment and gifts",
}

# 运费关键字
SHIPPING_KEYWORDS = [
    "parcel2go",
    "royal mail",
    "evri",
    "dhl",
    "dpd",
    "hermes",
    "yodel",
    "ups",
    "gls",
    "post office",
    "postage",
    "shipping",
    "delivery",
    "ecms",
    "parcel",
    "fedex",
    "tnt",
    "parcelforce",
]

# 包装材料关键字
PACKAGING_KEYWORDS = [
    "packaging",
    "packing",
    "carton",
    "cardboard box",
    "boxes",
    "box ",
    "bubble wrap",
    "mailers",
    "mailing bag",
    "padded bag",
    "jiffy",
    "tape",
    "胶带",
    "封箱",
    "void fill",
    "poly bag",
    "label printer",
    "dymo",
    "zebra",
]


def classify_item_type(category: str, description: str) -> str:
    """
    根据 Category + Description 自动识别：
    goods / refund / shipping / packaging / other_costs / other
    """
    cat = (category or "").strip()
    desc = (description or "").lower()

    if cat == "Refunds":
        return "refund"

    if any(k in desc for k in SHIPPING_KEYWORDS) or (
        cat == "Other direct costs" and "parcel" in desc
    ):
        return "shipping"

    if any(k in desc for k in PACKAGING_KEYWORDS):
        return "packaging"

    if cat == "Stock":
        return "goods"

    if cat in ("Business account fees", "Other direct costs"):
        return "other_costs"

    return "other"


def load_and_prepare(csv_path: str | Path) -> pd.DataFrame:
    """
    读取 ANNA CSV，清理数据，计算不含税成本和 VAT 金额，并打上 Item_Type。
    所有金额按 20% VAT 处理。
    为兼容 ANNA 新增的附件 URL 列，使用 csv.reader 手工按表头列数截断/补齐。
    """
    csv_path = Path(csv_path)
    print(f"[INFO] Loading CSV: {csv_path}")

    rows: list[list[str]] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)

        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("CSV 文件为空，无法生成报表")

        expected_cols = len(header)

        for line_no, row in enumerate(reader, start=2):
            # 跳过完全空行
            if not any(row):
                continue

            if len(row) < expected_cols:
                # 列数不足，补空字符串
                row = row + [""] * (expected_cols - len(row))
            elif len(row) > expected_cols:
                # 多余的列（例如多附件 URL），截断到表头列数
                row = row[:expected_cols]

            rows.append(row)

    df = pd.DataFrame(rows, columns=header)

    # 去掉全空列（多余的 Unnamed 列）
    df = df.dropna(axis=1, how="all")

    # 解析 Created 列，例如：2025-11-30, 23:35:36
    if "Created" not in df.columns:
        raise KeyError("CSV 中缺少 'Created' 列")

    df["Created_dt"] = pd.to_datetime(
        df["Created"].str.replace(",", ""),
        format="%Y-%m-%d %H:%M:%S",
    )

    # 金额
    if "Amount" not in df.columns:
        raise KeyError("CSV 中缺少 'Amount' 列")

    df["Amount"] = df["Amount"].astype(float)

    # 分类
    df["Item_Type"] = df.apply(
        lambda r: classify_item_type(
            r.get("Category", "") if "Category" in df.columns else "",
            r.get("Description", "") if "Description" in df.columns else "",
        ),
        axis=1,
    )

    # 过滤掉不需要 HK 承担的类别
    if "Category" in df.columns:
        before = len(df)
        df = df[~df["Category"].isin(EXCLUDE_CATEGORIES)].copy()
        after = len(df)
        print(f"[INFO] Filtered categories, {before} -> {after} rows")

    # 拆分 VAT（默认 20%）
    df["Net_Ex_VAT"] = (df["Amount"] / 1.2).round(2)
    df["VAT_Amount"] = (df["Amount"] - df["Net_Ex_VAT"]).round(2)

    return df


def infer_period_label(df: pd.DataFrame) -> str:
    """
    根据 Created_dt 推断期间标签，例如 '2025-10'。
    如跨多月，则用 'YYYYMMDD-YYYYMMDD'。
    """
    periods = df["Created_dt"].dt.to_period("M").unique()
    if len(periods) == 1:
        return str(periods[0])

    first = df["Created_dt"].min()
    last = df["Created_dt"].max()
    return f"{first:%Y%m%d}-{last:%Y%m%d}"


def generate_accounting_report(df: pd.DataFrame, out_path: Path) -> None:
    """
    生成记账用明细报表（Excel），包含：
    原始金额（Amount，含 VAT）、Net_Ex_VAT、VAT_Amount、Item_Type 等。
    （内部会计和 VAT 记录使用，和对外 CI 发票金额无冲突）
    """
    print(f"[INFO] Writing accounting report to: {out_path}")
    report = df.copy()
    report = report.rename(columns={"Created_dt": "Created_Parsed"})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_excel(out_path, index=False)


def generate_invoice_docx(df: pd.DataFrame, period_label: str, out_path: Path) -> None:
    """
    生成【成本 +15% 重售模式】的 DOCX 发票（与最新 Trade Agreement / Pricing Policy 对齐）：
    - 英国公司作为 Seller（卖方），香港公司作为 Buyer（买方）
    - UK Landed Cost = 所有 Net_Ex_VAT 合计（含商品、运费、包材等）
    - CI = UK Landed Cost × 1.15
    - 发票中不再向香港公司展示英国进项 VAT，只展示净成本和加价
    """
    print(f"[INFO] Generating DOCX invoice (cost+15% resale): {out_path}")

    exporter = FINANCE_EES.get("exporter", {})
    consignee = FINANCE_EES.get("consignee", {})
    bank = FINANCE_EES.get("bank", {})
    declaration_text = FINANCE_EES.get("declaration", "")

    # 基础成本 = 所有采购净额（不含VAT），注意 ANNA 支出为负，这里取反
    base_cost = round(-df["Net_Ex_VAT"].sum(), 2)

    # 成本 + 15% 定价
    mark_up_rate = 0.15
    mark_up_amount = round(base_cost * mark_up_rate, 2)
    sale_total = round(base_cost + mark_up_amount, 2)

    # 按 Item_Type 拆分净成本（只用于说明，不用来算价）
    by_type_net = (
        df.groupby("Item_Type")[["Net_Ex_VAT"]]
        .sum()
        .mul(-1)  # 变成正数
        .round(2)
        .reset_index()
    )

    invoice_no = f"EES-HK-{period_label.replace('-', '')}"
    today_str = datetime.today().strftime("%Y-%m-%d")

    doc = Document()

    # 标题 INVOICE
    title = doc.add_paragraph("INVOICE")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.runs[0]
    title_run.bold = True
    title_run.font.size = Pt(18)

    doc.add_paragraph()  # 空行

    # 上半部分：左 Seller（UK），右 Invoice Details
    table = doc.add_table(rows=4, cols=2)
    table.autofit = True

    # 左上：Seller 信息
    cell_left = table.cell(0, 0)
    p = cell_left.add_paragraph()
    p.add_run("Seller (UK)\n").bold = True
    p.add_run(f"{exporter.get('name', '')}\n")
    p.add_run(f"{exporter.get('address', '')}\n")
    p.add_run(f"Company No: {exporter.get('company_no', '')}\n")
    p.add_run(f"VAT No: {exporter.get('vat_no', '')}\n")
    p.add_run(f"EORI No: {exporter.get('eori_no', '')}\n")
    p.add_run(f"Phone: {exporter.get('phone', '')}\n")
    p.add_run(f"Email: {exporter.get('email', '')}")

    # 右上：Invoice Details
    cell_right = table.cell(0, 1)
    p = cell_right.add_paragraph()
    p.add_run("Invoice Details\n").bold = True
    p.add_run(f"Invoice No: {invoice_no}\n")
    p.add_run(f"Date: {today_str}\n")
    p.add_run(f"Billing Period: {period_label}\n")
    p.add_run("Currency: GBP\n")
    p.add_run("Pricing Model: UK landed cost × 1.15")

    # 第二行：Buyer (HK)
    cell_left2 = table.cell(1, 0)
    p = cell_left2.add_paragraph()
    p.add_run("Buyer (HK)\n").bold = True
    p.add_run(f"{consignee.get('name', '')}\n")
    p.add_run(f"{consignee.get('address', '')}\n")
    if consignee.get("phone"):
        p.add_run(f"Phone: {consignee.get('phone')}\n")
    if consignee.get("email"):
        p.add_run(f"Email: {consignee.get('email')}")

    # 第二行右：Bank Details
    cell_right2 = table.cell(1, 1)
    p = cell_right2.add_paragraph()
    p.add_run("Bank Details\n").bold = True
    p.add_run(f"Bank Name: {bank.get('bank_name', '')}\n")
    p.add_run(f"Account Name: {bank.get('account_name', '')}\n")
    p.add_run(f"Account Number: {bank.get('account_no', '')}\n")
    p.add_run(f"Sort Code: {bank.get('sort_code', '')}\n")
    if bank.get("iban"):
        p.add_run(f"IBAN: {bank.get("iban", "")}\n")
    if bank.get("swift"):
        p.add_run(f"SWIFT/BIC: {bank.get("swift", "")}")

    doc.add_paragraph()

    # Charges Summary 标题
    heading = doc.add_paragraph()
    run = heading.add_run("Charges Summary (Cost + 15% Resale)")
    run.bold = True
    run.font.size = Pt(12)

    doc.add_paragraph(
        "This invoice represents the resale of goods procured in the United Kingdom "
        "by the UK Seller to the Hong Kong Buyer. The resale price is based on the "
        "UK landed cost (exclusive of UK VAT) plus a 15% mark-up, in line with the "
        "agreed pricing policy."
    )

    # 成本拆分表（只显示 Net_Ex_VAT）
    charges_table = doc.add_table(rows=1, cols=2)
    hdr_cells = charges_table.rows[0].cells
    hdr_cells[0].text = "Cost Type"
    hdr_cells[1].text = "Net Cost (GBP, ex-UK VAT)"

    for _, row in by_type_net.iterrows():
        row_cells = charges_table.add_row().cells
        row_cells[0].text = str(row["Item_Type"])
        row_cells[1].text = f"{row['Net_Ex_VAT']:.2f}"

    # 总成本行
    total_row = charges_table.add_row().cells
    total_row[0].text = "Total UK landed cost"
    total_row[1].text = f"{base_cost:.2f}"

    # 空行 + 加价说明
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run(f"Mark-up rate: {int(mark_up_rate * 100)}%\n")
    p.add_run(f"Mark-up amount: GBP {mark_up_amount:.2f}\n").bold = True
    p.add_run(f"Total amount payable (Cost + Mark-up): GBP {sale_total:.2f}\n").bold = True

    doc.add_paragraph(
        "No UK VAT is charged on this invoice. The supply is treated as an export of goods "
        "from the United Kingdom to Hong Kong and is zero-rated for UK VAT, subject to "
        "valid export evidence being retained by the Seller."
    )

    # Declaration
    doc.add_paragraph()
    dec_heading = doc.add_paragraph()
    r = dec_heading.add_run("Declaration")
    r.bold = True
    if declaration_text:
        doc.add_paragraph(declaration_text)
    else:
        doc.add_paragraph(
            "The Seller confirms that the goods covered by this invoice are exported from the "
            "United Kingdom within the statutory time limit and that all supporting documents "
            "are retained for UK VAT zero-rating purposes."
        )

    # 签字栏
    doc.add_paragraph()
    sig_heading = doc.add_paragraph()
    r = sig_heading.add_run("Authorised Signature")
    r.bold = True

    doc.add_paragraph("For and on behalf of:")
    doc.add_paragraph(exporter.get("name", ""))

    doc.add_paragraph(" ")
    doc.add_paragraph("Signature: ______________________________")
    doc.add_paragraph("Name: ")
    doc.add_paragraph("Title: ")
    doc.add_paragraph("Date: ")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    print("[OK] DOCX invoice (cost+15% resale) generated.")


def generate_anna_monthly_reports(
    csv_path: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """
    供 pipeline 调用的主函数：
      - 输入：csv_path（ANNA CSV），output_dir（输出目录）
      - 输出：记账表（xlsx），正式发票（docx） 路径
    """
    output_dir = Path(output_dir)
    df = load_and_prepare(csv_path)
    period_label = infer_period_label(df)

    accounting_path = output_dir / f"anna_accounting_report_{period_label}.xlsx"
    invoice_path = output_dir / f"Invoice_UK_to_HK_{period_label}.docx"

    generate_accounting_report(df, accounting_path)
    generate_invoice_docx(df, period_label, invoice_path)

    print(f"[OK] Accounting report: {accounting_path}")
    print(f"[OK] Invoice DOCX: {invoice_path}")

    return accounting_path, invoice_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m finance.ingest.anna_monthly_reports <csv_path> <output_dir>")
    else:
        generate_anna_monthly_reports(sys.argv[1], sys.argv[2])
