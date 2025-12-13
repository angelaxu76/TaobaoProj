
import sys
from finance.ingest.manage_export_shipments_costs import export_poe_cost_template,import_poe_cost_from_excel

def main():
    poe_ids = [
    "SD10010276099707",
    ]

    for poe_id in poe_ids:
        output_path = fr"D:\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES\{poe_id}_costs.xlsx"
        export_poe_cost_template(poe_id, output_path)



if __name__ == "__main__":
    main()
