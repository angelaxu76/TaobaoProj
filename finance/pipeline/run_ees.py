import os
import psycopg2
from config import PGSQL_CONFIG
from finance.ingest.export_ees_pdf import (
    generate_export_evidence_pdf,
    generate_commercial_invoice_pdf,
)

OUTPUT_DIR = r"D:\OneDrive\CrossBorderDocs\06_Export_Proofs"


def main():
    conn = psycopg2.connect(**PGSQL_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT uk_invoice_no, folder_name FROM export_shipments_summary;"
    )
    rows = cur.fetchall()
    conn.close()

    for inv, folder in rows:
        # 目标目录
        folder_path = os.path.join(OUTPUT_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)

        # 两个目标文件
        ees_path = os.path.join(folder_path, f"ExportEvidenceSummary_{inv}.pdf")
        ci_path = os.path.join(folder_path, f"CommercialInvoice_{inv}.pdf")

        need_ees = not os.path.exists(ees_path)
        need_ci = not os.path.exists(ci_path)

        if not need_ees and not need_ci:
            print(f"[SKIP] {inv} EES & CI already exist.")
            continue

        print(
            f"[RUN] Generating for {inv} ... "
            f"(EES: {'YES' if need_ees else 'NO'}, CI: {'YES' if need_ci else 'NO'})"
        )

        try:
            if need_ees:
                generate_export_evidence_pdf(inv)
            if need_ci:
                generate_commercial_invoice_pdf(inv)
        except Exception as e:
            print(f"[ERROR] {inv}: {e}")


if __name__ == "__main__":
    main()
