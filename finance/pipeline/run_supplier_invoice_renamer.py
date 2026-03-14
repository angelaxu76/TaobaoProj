
import sys
from finance.supplier.rename_camper_invoices  import rename_camper_invoices
from finance.supplier.rename_clarks_invoices  import rename_clarks_invoices
from finance.supplier.rename_ecco_invoices    import rename_ecco_invoices
from finance.supplier.rename_amazon_invoices       import rename_amazon_invoices
from finance.supplier.rename_parcelbroker_receipts import rename_parcelbroker_receipts

def main():
    # rename_camper_invoices(
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\camper_invoice\original-202602",
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\202512-202602\camper",
    # )

    rename_clarks_invoices(
        r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\clarks invoice\orgl-202603",
        r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\202512-202602\clarks",
    )

    # rename_ecco_invoices(
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\ecco_invoice\original-202602",
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\202512-202602\ECCO",
    # )

    # rename_amazon_invoices(
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\amazon_invoice\202602",
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\202512-202602\AMZ",
    # )

    # rename_parcelbroker_receipts(
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\99_Backup\parcelbroker",
    #     r"C:\Users\angel\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\202512-202602\parcelbroker",
    # )

if __name__ == "__main__":
    main()
