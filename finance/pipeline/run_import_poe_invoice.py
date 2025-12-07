
import sys
from finance.ingest.batch_import_export_shipments import import_poe_invoice

def main():
    import_poe_invoice(r"D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs")

if __name__ == "__main__":
    main()
