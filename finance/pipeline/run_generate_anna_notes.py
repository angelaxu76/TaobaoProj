import os
from finance.ingest.generate_anna_notes import make_anna_notes_with_auto_po

def main():
    supplier = "EMINZORA"          # 公司简称；也可作为 company_short
    brand = "camper"
    output_dir = r"D:\OneDrive\CrossBorderDocs\03_Purchase_Records\PO\202510"
    shipment_ids = ["78948826215326"]
    order_id = "4007411370"        # 原 order_no -> order_id
    order_date = "2025-10-17"      # 原 po_date -> order_date (YYYY-MM-DD 或 YYYYMMDD)

    os.makedirs(output_dir, exist_ok=True)

    # 先生成 Anna 备注（不传 output_txt）
    po_number, notes, not_found = make_anna_notes_with_auto_po(
        supplier=supplier,
        brand=brand,
        shipment_ids=shipment_ids,
        order_date=order_date,
        order_id=order_id,
        company_short=supplier
    )

    # 再用 po_number 拼文件名
    output_txt = os.path.join(output_dir, f"{po_number}.txt")
    with open(output_txt, "w", encoding="utf-8") as f:
        for line in notes:
            f.write(line + "\n")

    print("PO Number:", po_number)
    print("Notes file:", output_txt)
    if not_found:
        print("未在数据库找到的 shipment_id:", not_found)

if __name__ == "__main__":
    main()
