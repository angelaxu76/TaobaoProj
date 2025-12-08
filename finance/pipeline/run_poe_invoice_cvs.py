from finance.ingest.generate_poe_invoice import generate_poe_invoice_and_report
from finance.ingest.generate_poe_ees_pdf import generate_poe_ees_pdf
BASE_DIR = r"D:\OneDrive\CrossBorderDocs_UK\99_Backup\POE_TEMPLATES"


# def export_cost_template_for_poe(poe_id: str):
#     output_path = fr"{BASE_DIR}\{poe_id}_costs.xlsx"
#     return export_poe_cost_template(poe_id, output_path)


# def import_cost_template_for_poe(poe_id: str):
#     excel_path = fr"{BASE_DIR}\{poe_id}_costs.xlsx"
#     return import_poe_cost_from_excel(excel_path)


def main():
    poe_id = "SD10009905718779"

    # 你希望输出到哪个文件夹：
    output_dir = r"D:\OneDrive\CrossBorderDocs_UK\06_Export_Proofs\SD10009905718779"

    excel_path, docx_path, pdf_path = generate_poe_invoice_and_report(poe_id, output_dir)
    generate_poe_ees_pdf(poe_id, output_dir)

    print("[DONE] Excel 报表:", excel_path)
    print("[DONE] Invoice DOCX:", docx_path)
    print("[DONE] Invoice PDF :", pdf_path)



if __name__ == "__main__":
    main()