import pandas as pd
from pathlib import Path
from typing import Optional

def generate_ci_excel(
    input_csv_anna: str,
    output_excel: Optional[str] = None,
    invoice_name: Optional[str] = None,
    vat_rate: float = 0.20,
    margin: float = 0.15,
) -> str:
    """
    从 ANNA 导出的交易 CSV 生成用于 CI 的 Excel 明细文件（可在 pipeline 中直接调用）。

    功能：
    - 读取 ANNA CSV（包含 Created, Amount, Description, Category 等）
    - 统一按 vat_rate 还原不含税金额 Net_Amount_Excl_VAT
    - 自动标记交易类型：Purchase / Refund（基于 Amount 正负）
    - 生成 CI_Amount 列：基于 Net_Amount_Excl_VAT * (1 + margin)，并保持“采购为正，退款为负”的逻辑：
        CI_Amount = - Net_Amount_Excl_VAT * (1 + margin)
      这样：
        - Purchase: Net_Amount_Excl_VAT 为负数 → CI_Amount 为正（记入发票）
        - Refund:   Net_Amount_Excl_VAT 为正数 → CI_Amount 为负（冲减发票）
    - 可选：如果传入 invoice_name，则在每一行增加 Invoice_Name 列，方便后续筛选或做月度汇总。
    """
    input_path = Path(input_csv_anna)
    if output_excel is None:
        output_path = input_path.with_suffix(".ci_detail.xlsx")
    else:
        output_path = Path(output_excel)

    # 读取 CSV，自动跳过坏行
    df = pd.read_csv(input_path, engine="python", on_bad_lines="skip")

    # 处理日期
    if "Created" not in df.columns:
        raise ValueError("CSV 中缺少 'Created' 列，请检查 ANNA 导出的格式。")
    df["Created_date"] = df["Created"].astype(str).str.split(",").str[0]
    df["Created_date"] = pd.to_datetime(df["Created_date"], errors="coerce")

    # 金额
    if "Amount" not in df.columns:
        raise ValueError("CSV 中缺少 'Amount' 列，请检查 ANNA 导出的格式。")
    gross = df["Amount"].astype(float)

    # 类型：退款 / 付款
    df["Type"] = gross.apply(lambda x: "Refund" if x > 0 else "Purchase")

    # VAT 拆分：含税 → 不含税
    net = gross / (1.0 + vat_rate)
    vat = gross - net

    df["Gross_Amount_GBP"] = gross.round(2)
    df["Net_Amount_Excl_VAT"] = net.round(2)
    df["VAT_Amount"] = vat.round(2)

    # CI 金额：基于不含税金额 * (1 + margin)，并反转符号
    df["CI_Amount"] = (-df["Net_Amount_Excl_VAT"] * (1.0 + margin)).round(2)

    # 可选：发票/批次名称
    if invoice_name is not None:
        df["Invoice_Name"] = str(invoice_name)

    # 选取常用列（若不存在某些列，则自动跳过）
    cols = ["Created_date"]
    for col in ["Description", "Category"]:
        if col in df.columns:
            cols.append(col)
    cols += ["Type", "Gross_Amount_GBP", "Net_Amount_Excl_VAT", "VAT_Amount", "CI_Amount"]
    for col in ["Currency", "Document"]:
        if col in df.columns:
            cols.append(col)
    if "Invoice_Name" in df.columns:
        cols.append("Invoice_Name")

    detail_df = df[cols].copy()

    # 写入 Excel
    detail_df.to_excel(output_path, index=False)
    return str(output_path)
