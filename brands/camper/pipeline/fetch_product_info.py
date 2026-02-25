from config import CAMPER
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.camper.legacy.fetch_product_info import camper_fetch_product_info,camper_retry_missing_once
from brands.camper.collect_product_links import camper_get_links
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_for_brand
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand


def main():
    # print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(CAMPER)

    # print("\n🟡 Step: 2️⃣ 抓取商品链接")
    # camper_get_links()

    # print("\n🟡 Step: 3️⃣ 抓取商品信息")
    # camper_fetch_product_info()
    # camper_retry_missing_once()

    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\camper\publication\missing_product_links.txt";
    generate_missing_links_for_brand("camper",missing_product_link )
    camper_fetch_product_info(missing_product_link )

    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
