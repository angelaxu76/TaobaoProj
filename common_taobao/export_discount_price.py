def calculate_final_price(price):
    try:
        return round((price * 1.2 + 18) * 1.1 * 1.2 * 9.7, 2)
    except:
        return None

def export_discount_excel(txt_dir, brand, output_excel):
    import os
    import pandas as pd

    rows = []
    for file in os.listdir(txt_dir):
        if file.endswith(".txt"):
            path = os.path.join(txt_dir, file)
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            product_code = ""
            actual_price = ""
            original_price = ""

            for line in lines:
                if line.startswith("Product Code:"):
                    product_code = line.replace("Product Code:", "").strip()
                elif line.startswith("Actual Price:"):
                    actual_price = line.replace("Actual Price:", "").replace("£", "").strip()
                elif line.startswith("Original Price:"):
                    original_price = line.replace("Original Price:", "").replace("£", "").strip()

            price = None
            try:
                price = float(actual_price or original_price)
            except:
                continue

            final_price = calculate_final_price(price)
            rows.append([product_code, final_price])

    df = pd.DataFrame(rows, columns=["商家编码", "优惠后价"])
    df.to_excel(output_excel, index=False)
    print(f"✅ 导出成功: {output_excel}")
