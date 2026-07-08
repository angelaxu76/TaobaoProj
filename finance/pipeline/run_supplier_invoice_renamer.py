
import sys
from finance.supplier.rename_camper_invoices  import rename_camper_invoices
from finance.supplier.rename_clarks_invoices  import rename_clarks_invoices
from finance.supplier.rename_ecco_invoices    import rename_ecco_invoices
from finance.supplier.rename_amazon_invoices       import rename_amazon_invoices
from finance.supplier.rename_parcelbroker_receipts import rename_parcelbroker_receipts
from config import ONEDRIVE_UK_DIR

def main():
    # rename_camper_invoices(
    #     str(ONEDRIVE_UK_DIR / "99_Backup" / "camper_invoice" / "added"),
    #     str(ONEDRIVE_UK_DIR / "03_Purchase_Records" / "01_Supplier_Invoices" / "202503-202605" / "camper"),
    # )

    rename_clarks_invoices(
        str(ONEDRIVE_UK_DIR / "99_Backup" / "clarks invoice" / "orginal-202605"),
        str(ONEDRIVE_UK_DIR / "03_Purchase_Records" / "01_Supplier_Invoices" / "202503-202605" / "Clarks-1"),
    )

    # rename_ecco_invoices(
    #     str(ONEDRIVE_UK_DIR / "99_Backup" / "ecco_invoice" / "orig-202605"),
    #     str(ONEDRIVE_UK_DIR / "03_Purchase_Records" / "01_Supplier_Invoices" / "202503-202605" / "ECCO"),
    # )

    # rename_amazon_invoices(
    #     str(ONEDRIVE_UK_DIR / "99_Backup" / "amazon_invoice" / "202602"),
    #     str(ONEDRIVE_UK_DIR / "03_Purchase_Records" / "01_Supplier_Invoices" / "202512-202602" / "AMZ"),
    # )

    # rename_parcelbroker_receipts(
    #     str(ONEDRIVE_UK_DIR / "99_Backup" / "parcelbroker"),
    #     str(ONEDRIVE_UK_DIR / "03_Purchase_Records" / "01_Supplier_Invoices" / "202512-202602" / "parcelbroker"),
    # )

if __name__ == "__main__":
    main()
