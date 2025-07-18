import os
import subprocess
from config import CAMPER
from common_taobao.jingya.import_channel_info_from_excel import parse_and_update_excel
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_all_sku_price_excel
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from common_taobao.jingya.import_txt_to_db_supplier import import_txt_to_db_supplier
from common_taobao.jingya.disable_low_stock_product import disable_low_stock_products
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel
from common_taobao.generate_discount_price_excel import export_store_discount_price
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from brands.camper.generate_publish_excels_from_db import


def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(CAMPER)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    #run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    #run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于3的直接设置成0")
    #import_txt_to_db_supplier("camper")  # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    #parse_and_update_excel("camper")

    print("\n🟡 Step: 5️⃣ 找出尺码很少的商品ID，将它所有的尺码都设置成0，并将状态变成未发布，为下一步该库存做准备")
    disable_low_stock_products("camper")

    print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    export_gender_split_excel("camper")

    print("\\n🟡 Step: 6️⃣ 导出渠道价格 Excel（含零售价与商家编码），可以用于淘宝店铺去更新商品价格")
    export_channel_price_excel("camper")  # 导出价格明细（已发布）
    # export_all_sku_price_excel("camper")  # 导出商家编码价格表（所有商品）

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")


    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    # export_skuid_stock_excel("camper")

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    store_list = ["五小剑", "英国伦敦代购2015"]
    for store in store_list:
        export_store_discount_price("camper", store)  # ✅ 导出价格文件

    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
