
import sys
from finance.ingest.batch_import_export_shipments import import_poe_invoice

def main():
    import_poe_invoice(r"D:\OneDrive\CrossBorderDocs_HK\06_Shipping_And_Export\POE_Reference_Copies")

if __name__ == "__main__":
    main()
