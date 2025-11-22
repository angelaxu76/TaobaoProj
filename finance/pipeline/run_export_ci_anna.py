import sys
from finance.ingest.generate_ci_excel_from_anna import generate_ci_excel

def main():
    generate_ci_excel(
    input_csv_anna=r"D:\OneDrive\CrossBorderDocs\03_Purchase_Records\02_Payment_Records\anna_bank\2025-10.csv",
    output_excel=r"D:\OneDrive\CrossBorderDocs_UK\02_Invoices\Commercial\CI_Generated\CI_Detail_2025-10.xlsx",
    invoice_name="CI-2025-10",
    )
if __name__ == "__main__":
    main()
