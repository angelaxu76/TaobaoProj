import os
import subprocess
from config import GEOX,TAOBAO_STORES
from pathlib import Path
from common_taobao.generate_discount_price_excel import export_price_with_itemid,export_store_discount_price
from common_taobao.export_skuid_stock import export_skuid_stock_excel
from common_taobao.import_txt_to_db import import_txt_to_db
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.generate_discount_price_excel import export_store_discount_price,export_discount_price_with_skuids
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(GEOX)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    #run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    #run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    #import_txt_to_db("geox")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    #export_skuid_stock_excel("geox")

    #for store in TAOBAO_STORES:
        #export_discount_price_with_skuids("geox", store)

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    for store in TAOBAO_STORES:
        #generate_product_excels(GEOX, store)
        codes = get_publishable_product_codes(GEOX, store)
        copy_images_for_store(GEOX, store, codes)

    print("\n✅ GEOX pipeline 完成")

if __name__ == "__main__":
    main()
