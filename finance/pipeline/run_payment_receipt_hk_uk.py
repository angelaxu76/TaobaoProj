import traceback
from finance.ingest.generate_payment_receipt import generate_payment_receipt_docx

def main():

    generate_payment_receipt_docx(
        payment_date="2025-11-20",
        amount_gbp=3900,
        output_path=r"D:\OneDrive\CrossBorderDocs_UK\04_PaymentProofs\HK_to_UK",
        closing_balance=23080.0,   # 来自 Intercompany_Ledger 的余额
        hk_ref="P1129933304",               # 没有就写 None 或不传
        uk_ref=None,               # ANNA 没有 ref 就 None
    )

if __name__ == "__main__":
    main()
