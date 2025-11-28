from config import CAMPER
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.camper.fetch_product_info import camper_fetch_product_info,camper_retry_missing_once
from brands.camper.collect_product_links import camper_get_links
from common_taobao.publication.export_low_stock_products import export_low_stock_for_brand


def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CAMPER)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    camper_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    camper_fetch_product_info()
    camper_retry_missing_once()

    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
