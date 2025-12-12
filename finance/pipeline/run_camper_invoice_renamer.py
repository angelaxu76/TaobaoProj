
import sys
from finance.supplier.rename_camper_invoices import rename_camper_invoices
from finance.supplier.rename_clarks_invoices import rename_clarks_invoices

def main():
    rename_camper_invoices(r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\camper_invoice\original", 
                           r"D:\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\camper"
    )

    # total, renamed, log_path = rename_clarks_invoices(
    # r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\clarks invoice\original",
    # r"D:\OneDrive\CrossBorderDocs_UK\03_Purchase_Records\01_Supplier_Invoices\clarks",
    # )
    # print(total, renamed, log_path)

if __name__ == "__main__":
    main()
