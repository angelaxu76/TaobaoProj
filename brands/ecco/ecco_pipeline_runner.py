import os
import subprocess
from config import ECCO,TAOBAO_STORES
from pathlib import Path
from common_taobao.generate_discount_price_excel import export_store_discount_price,export_discount_price_with_skuids
from common_taobao.export_skuid_stock import export_skuid_stock_excel
from common_taobao.import_txt_to_db import import_txt_to_db
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs  # ✅ 新增导入
from brands.ecco.unified_link_collector import ecco_get_links
from brands.ecco.fetch_product_info import ecco_fetch_info
#

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(ECCO)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    ecco_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    ecco_fetch_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    import_txt_to_db("ecco")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    export_skuid_stock_excel("ecco")

    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    for store in TAOBAO_STORES:
        export_discount_price_with_skuids("ecco", store)

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    for store in TAOBAO_STORES:
        generate_product_excels(ECCO, store)
        codes = get_publishable_product_codes(ECCO, store)
        copy_images_for_store(ECCO, store, codes)

    print("\n✅ ECCO pipeline 完成")

if __name__ == "__main__":
    main()
