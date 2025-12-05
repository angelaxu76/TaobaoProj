import traceback
from finance.ingest.anna_monthly_reports_v2 import generate_anna_monthly_reports

def main():
    try:
        csv_file = r"D:\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\02_Payment_Records\anna_bank\2025-11.csv"
        output_dir = r"D:\OneDrive\CrossBorderDocs_UK\02_Invoices\Commercial\CI_Generated"

        acc_path, inv_path = generate_anna_monthly_reports(csv_file, output_dir)
        print("[SUCCESS]", acc_path, inv_path)

    except Exception as e:
        print("\n[ERROR OCCURRED]\n")
        traceback.print_exc()

if __name__ == "__main__":
    main()
