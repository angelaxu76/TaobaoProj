
import sys
from finance.ingest.batch_import_export_shipments import import_poe_invoice
from config import ONEDRIVE_HK_DIR

def main():
    import_poe_invoice(str(ONEDRIVE_HK_DIR / "06_Shipping_And_Export" / "POE_References"))

if __name__ == "__main__":
    main()
