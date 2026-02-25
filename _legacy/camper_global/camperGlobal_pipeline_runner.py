import os
import subprocess
from config import CAMPER_GLOBAL
from channels.jingya.ingest.import_channel_info import insert_JingyaId_toDB
from _legacy.camper_global.generate_camper_publish_excel import generate_camper_publish_excel
from channels.jingya.export.prepare_utils_extended import copy_images_for_store, get_publishable_product_codes


def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(CAMPER_GLOBAL)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    # run_script("collect_product_links.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    #run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    #import_camper_global_txt_to_db()  # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）")
    #parse_and_update_excel("camper")

    print("\\n🟡 Step: 6️⃣ 导出渠道价格 Excel（含零售价与商家编码）")
    #export_channel_price_excel("camper")  # 导出价格明细（已发布）
    #export_all_sku_price_excel("camper")  # 导出商家编码价格表（所有商品）

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    # export_skuid_stock_excel("camper")

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    store_list = ["五小剑", "英国伦敦代购2015"]
    for store in store_list:
     #export_store_discount_price("camper", store)  # ✅ 导出价格文件
     generate_camper_publish_excel(store)
     codes = get_publishable_product_codes(CAMPER_GLOBAL, store)
     copy_images_for_store(CAMPER_GLOBAL, store, codes)

    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
