from pathlib import Path
from brands.camper.collect_product_links_manual import generate_camper_product_links
from brands.camper.legacy.find_taobaoID_from_url import extract_product_codes_from_txt,find_item_ids_from_url_links,find_item_ids_from_code_txt

txt_path = Path(r"D:\TB\Products\camper\publication\product_links.txt")
output_path = txt_path.parent / "product_codes.txt"

codes = extract_product_codes_from_txt(txt_path, output_path)
# ✅ codes 为提取后的编码列表，可供后续逻辑使用


def main():
    print("\n🟡 Step: 2️⃣ 抓取新品商品链接")
    generate_camper_product_links()


    txt_path = Path(r"D:\TB\Products\camper\publication\product_links.txt")
    output_path = txt_path.parent / "product_codes.txt"

    codes = extract_product_codes_from_txt(txt_path, output_path)
# ✅ codes 为提取后的编码列表，可供后续逻辑使用

    find_item_ids_from_url_links("camper")

    find_item_ids_from_code_txt("camper", Path(r"D:\TB\Products\camper\repulibcation\id_code.txt"))

if __name__ == "__main__":
    main()