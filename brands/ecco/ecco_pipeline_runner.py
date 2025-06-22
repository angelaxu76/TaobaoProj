import os
import subprocess
from config import ECCO
from pathlib import Path
from common_taobao.generate_discount_price_excel import export_discount_price_excel
from common_taobao.export_skuid_stock import export_skuid_stock_excel
from common_taobao.import_txt_to_db import import_txt_to_db
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs  # ✅ 新增导入

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(ECCO)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    #run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    #run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    #import_txt_to_db("ecco")

    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    #export_discount_price_excel("ecco")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    #export_skuid_stock_excel("ecco")

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    store_list = ["五小剑", "英国伦敦代购2015"]
    for store in store_list:
        generate_product_excels(ECCO, store)
        codes = get_publishable_product_codes(ECCO, store)
        copy_images_for_store(ECCO, store, codes)

    print("\n✅ ECCO pipeline 完成")

if __name__ == "__main__":
    main()
