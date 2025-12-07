
import sys
from finance.ingest.manage_export_shipments_costs import export_poe_cost_template,import_poe_cost_from_excel

def main():
    poe_ids = [
    "SD10009849381617",
    "SD10009875605045",
    "SD10009887634724",
    "SD10009861120760",
    "SD10009872426397",
    "SD10009905718779",
    "SD10009918435780",
    "SD10009947517700",
    "SD10009958784764",
    "SD10010045465948",
    "SD10010000471683",
    "SD10010091926843",
    "SD10010107872414",
    "SD10010084702872",
    "SD10010097776771",
    "SD10010129248974",
    "SD10010142281499",
    "SD10010232793342",
    "SD10010245825217",
    ]

    for poe_id in poe_ids:
        output_path = fr"D:\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES\{poe_id}_costs.xlsx"
        export_poe_cost_template(poe_id, output_path)



if __name__ == "__main__":
    main()
