import pandas as pd
from pathlib import Path
from datetime import datetime

from finance_config import FINANCE_EES  # 使用你现有的配置文件


# 默认不向香港公司收费的类别（可以按需要修改）
EXCLUDE_CATEGORIES = {
    "Personal expenses",
    "Sales",
    "Non-taxable income",
    "Client entertainment and gifts",
}


# 运费和打包材料的关键字（可以根据你自己的记录慢慢微调）
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

    # 运费识别：Category 是 Other direct costs 或描述中有物流关键字
    if any(k in desc for k in SHIPPING_KEYWORDS) or (
        cat == "Other direct costs" and "parcel" in desc
    ):
        return "shipping"

    # 打包材料识别
    if any(k in desc for k in PACKAGING_KEYWORDS):
        return "packaging"

    # 采购商品
    if cat == "Stock":
        return "goods"

    # 其他直接成本 / 账户费用
    if cat in ("Business account fees", "Other direct costs"):
        return "other_costs"

    return "other"


def load_and_prepare(csv_path: str | Path) -> pd.DataFrame:
    """
    读取 ANNA CSV，清理数据，计算不含税成本和 VAT 金额，并打上 Item_Type。
    所有金额按 20% VAT 处理。
    """
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    # 去掉全空列（多余的 Unnamed 列）
    df = df.dropna(axis=1, how="all")

    # 解析创建时间（Created），例如：2025-10-30, 23:35:36
    df["Created_dt"] = pd.to_datetime(
        df["Created"].str.replace(",", ""),
        format="%Y-%m-%d %H:%M:%S",
    )

    # 金额转 float
    df["Amount"] = df["Amount"].astype(float)

    # 根据 Category + Description 自动识别类型
    df["Item_Type"] = df.apply(
        lambda r: classify_item_type(r.get("Category", ""), r.get("Description", "")),
        axis=1,
    )

    # 过滤掉不需要香港公司承担的类别
    if "Category" in df.columns:
        df = df[~df["Category"].isin(EXCLUDE_CATEGORIES)].copy()

    # 按 20% VAT 拆分：
    # 含税金额 = 不含税 * 1.2 => 不含税 = 含税 / 1.2
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
    - 原始金额（Amount，含 VAT）
    - Net_Ex_VAT（不含税成本）
    - VAT_Amount（对应 VAT）
    - Item_Type（goods/refund/shipping/packaging/other...）
    以及原始描述 / 类别 / 单据链接等。
    """
    report = df.copy()
    report = report.rename(columns={"Created_dt": "Created_Parsed"})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_excel(out_path, index=False)


def generate_invoice(df: pd.DataFrame, period_label: str, out_path: Path) -> None:
    """
    生成英国公司给香港公司的 Invoice 文本（.txt），
    使用 finance_config.FINANCE_EES 中的公司信息，
    并按 Item_Type 汇总金额。
    """
    exporter = FINANCE_EES["exporter"]
    consignee = FINANCE_EES["consignee"]

    # Amount 在银行流水里：支出为负数，收入为正数
    # 向香港公司收费时，需要取反：支出 → 正数，退款 → 负数（抵减）
    total_gross = round(-df["Amount"].sum(), 2)
    total_net = round(-df["Net_Ex_VAT"].sum(), 2)
    total_vat = round(-df["VAT_Amount"].sum(), 2)

    # 按 Item_Type 汇总（goods/refund/shipping/packaging/...）
    by_type = (
        df.groupby("Item_Type")[["Amount", "Net_Ex_VAT", "VAT_Amount"]]
        .sum()
        .mul(-1)   # 取反：变成“向香港公司收取”的正数
        .round(2)
        .reset_index()
    )

    invoice_no = f"EES-HK-{period_label.replace('-', '')}"

    lines = []
    lines.append(f"INVOICE: {invoice_no}")
    lines.append("")
    lines.append("Exporter (UK):")
    lines.append(f"  {exporter['name']}")
    lines.append(f"  {exporter['address']}")
    lines.append(f"  Company No: {exporter['company_no']}")
    lines.append(f"  VAT No: {exporter['vat_no']}")
    lines.append("")
    lines.append("Consignee (HK):")
    lines.append(f"  {consignee['name']}")
    lines.append(f"  {consignee['address']}")
    lines.append("")
    lines.append(f"Period: {period_label}")
    lines.append("")
    lines.append("Breakdown by type (amounts in GBP):")
    lines.append("")
    lines.append(f"{'Type':15} {'Gross':>12} {'Net ex VAT':>12} {'VAT (20%)':>10}")

    for _, row in by_type.iterrows():
        lines.append(
            f"{str(row['Item_Type'])[:15]:15} "
            f"{row['Amount']:12.2f} "
            f"{row['Net_Ex_VAT']:12.2f} "
            f"{row['VAT_Amount']:10.2f}"
        )

    lines.append("")
    lines.append(f"Total gross (bank movements, for reference): {total_gross:.2f} GBP")
    lines.append(f"Total net amount payable (excl. UK VAT):    {total_net:.2f} GBP")
    lines.append(f"Corresponding UK VAT (not charged to HK):   {total_vat:.2f} GBP")
    lines.append("")
    lines.append(
        "All transactions relate to procurement, shipping, packaging and related "
        "expenses incurred by the UK exporter on behalf of the HK company."
    )
    lines.append(
        "Supply is treated as export of goods, zero-rated for UK VAT. "
        "The HK company reimburses the net cost only."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# 🔹 你可以在 pipeline 里直接调用这个函数
def generate_anna_monthly_reports(
    csv_path: str | Path,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """
    供外部 pipeline 调用的主函数。

    参数：
      - csv_path: ANNA 下载的交易记录 CSV 路径
      - output_dir: 输出目录

    返回：
      - (accounting_report_path, invoice_path)
    """
    output_dir = Path(output_dir)
    df = load_and_prepare(csv_path)
    period_label = infer_period_label(df)

    accounting_path = output_dir / f"anna_accounting_report_{period_label}.xlsx"
    invoice_path = output_dir / f"invoice_uk_to_hk_{period_label}.txt"

    generate_accounting_report(df, accounting_path)
    generate_invoice(df, period_label, invoice_path)

    print(f"[OK] Accounting report: {accounting_path}")
    print(f"[OK] Invoice: {invoice_path}")

    return accounting_path, invoice_path


# 可选：命令行单独运行（不影响你在 pipeline 中 import 调用）
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python anna_monthly_reports.py <csv_path> <output_dir>")
    else:
        generate_anna_monthly_reports(sys.argv[1], sys.argv[2])
