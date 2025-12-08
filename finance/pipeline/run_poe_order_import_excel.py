from finance.ingest.manage_export_shipments_costs import import_poe_cost_from_excel

BASE_DIR = r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES"

def main():
    poe_id = "SD10009905718779"
    output_path = fr"{BASE_DIR}\{poe_id}_costs.xlsx"
    filepath = import_poe_cost_from_excel(output_path)
    print("[OK] 生成模板：", filepath)

if __name__ == "__main__":
    main()