
import sys
from finance.camper.rename_camper_invoices import rename_invoices

def main():
    rename_invoices(r"D:\TB\Invoice\camper\original", r"D:\TB\Invoice\camper\customizeName")

if __name__ == "__main__":
    main()
