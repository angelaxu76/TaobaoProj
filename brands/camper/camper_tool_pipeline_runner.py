from config import CAMPER
from pathlib import Path
from brands.camper.unified_link_specify_collector import generate_camper_product_links
from brands.camper.tools.find_taobaoID_from_url import extract_product_codes_from_txt

txt_path = Path(r"D:\TB\Products\camper\publication\product_links.txt")
output_path = txt_path.parent / "product_codes.txt"

codes = extract_product_codes_from_txt(txt_path, output_path)
# ✅ codes 为提取后的编码列表，可供后续逻辑使用


def main():
    print("\n🟡 Step: 2️⃣ 抓取新品商品链接")
    #generate_camper_product_links()


    txt_path = Path(r"D:\TB\Products\camper\publication\product_links.txt")
    output_path = txt_path.parent / "product_codes.txt"

    codes = extract_product_codes_from_txt(txt_path, output_path)
# ✅ codes 为提取后的编码列表，可供后续逻辑使用


if __name__ == "__main__":
    main()