import os
import subprocess
from pathlib import Path
from config import REISS
from brands.reiss.core.reiss_link_collector import reiss_get_links
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from brands.reiss.core.reiss_product_fetcher import reiss_fetch_all
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.core.generate_publication_excel_outerwear import generate_publication_excels_clothing
from brands.reiss.core.download_reiss_images import download_reiss_images_from_codes

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(REISS)

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    DEFAULT_CATEGORIES = REISS.get("CATEGORY_BASE_URLS", [])
    cats = DEFAULT_CATEGORIES or [
        "https://www.reiss.com/shop/feat-sale-gender-women-0",
        "https://www.reiss.com/shop/feat-sale-gender-men-0",
    ]
    reiss_get_links(cats, headless=True)

    print("\\n🟡 Step: 6️⃣下载商品信息写入TXT")
    reiss_fetch_all()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    import_txt_to_db_supplier("reiss")  # ✅ 新逻辑

    print("\n🟡 Step: 4️⃣ 生成发布产品的excel")
    generate_publication_excels_clothing(brand="reiss",pricing_mode="taobao",min_sizes=3,min_total_stock=6,gender_filter="women", category_filter=["Dresses"])

    
    print("\n🟡 Step: 4️⃣ 下载指定编码的图片")
    sample_codes_file = Path(r"D:\TB\Products\reiss\repulibcation\publication_codes_outerwear.txt")
    download_reiss_images_from_codes(sample_codes_file)


if __name__ == "__main__":
    main()
