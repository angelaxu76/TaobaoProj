
import os, psycopg2
from config import PGSQL_CONFIG
from finance.ingest.export_ees_pdf import generate_export_evidence_pdf

OUTPUT_DIR = r"D:\OneDrive\CrossBorderDocs\06_Export_Proofs"

def main():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT uk_invoice_no, folder_name FROM export_shipments_summary;")
    rows = cur.fetchall()
    conn.close()

    for inv, folder in rows:
        pdf_path = os.path.join(OUTPUT_DIR, folder, f"ExportEvidenceSummary_{inv}.pdf")
        if os.path.exists(pdf_path):
            print(f"[SKIP] {inv} already exists.")
            continue

        print(f"[RUN] Generating {inv} ...")
        try:
            generate_export_evidence_pdf(inv)
        except Exception as e:
            print(f"[ERROR] {inv}: {e}")

if __name__ == "__main__":
    main()
