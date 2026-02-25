import os
import subprocess
from config import BIRKENSTOCK,TAOBAO_STORES
from channels.jingya.export.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes


#
def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(BIRKENSTOCK)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    #run_script("collect_product_links.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    #run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    #import_txt_to_db("birkenstock")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    #export_skuid_stock_excel("birkenstock")

    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    #for store in TAOBAO_STORES:
        #export_discount_price_with_skuids("birkenstock", store)

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    for store in TAOBAO_STORES:
     generate_product_excels(BIRKENSTOCK, store)
     codes = get_publishable_product_codes(BIRKENSTOCK, store)
     copy_images_for_store(BIRKENSTOCK, store, codes)

    print("\n✅ ECCO pipeline 完成")

if __name__ == "__main__":
    main()
