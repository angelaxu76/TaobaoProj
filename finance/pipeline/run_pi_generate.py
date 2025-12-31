
import sys
from datetime import date
from pathlib import Path
from finance.ingest.generate_proforma_invoice_pdf import generate_pi_simple

def main():
    pdf = generate_pi_simple(
    amount_gbp=7700,
    inv_date=date(2025, 12, 15),
    out_dir=Path(r"D:\OneDrive\CrossBorderDocs_UK\04_PaymentProofs\HK_PI"),
    )

if __name__ == "__main__":
    main()
