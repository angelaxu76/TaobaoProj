import os
import subprocess
from config import CAMPER
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_all_sku_price_excel,export_channel_price_excel_from_txt
from common_taobao.jingya.jingya_export_stockcount_to_excel import export_stock_excel
from common_taobao.jingya.jiangya_export_channel_price_excel import export_jiangya_channel_prices
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.jingya.disable_low_stock_product import disable_low_stock_products
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel
from common_taobao.generate_discount_price_excel import export_store_discount_price
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from common_taobao.generate_taobao_store_price_for_import_excel import generate_price_excel
from brands.camper.fetch_product_info import camper_fetch_product_info
from brands.camper.unified_link_collector import camper_get_links
from common_taobao.export_low_stock_products import export_low_stock_for_brand


def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(CAMPER)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    # camper_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    # camper_fetch_product_info()

    # print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    # import_txt_to_db_supplier("camper")  # ✅ 新逻辑

    # print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    # insert_jingyaid_to_db("camper")

    # print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    # insert_missing_products_with_zero_stock("camper")

    print("\n🟡 Step: 5️⃣ 找出尺码很少的商品ID，将它所有的尺码都设置成0，并将状态变成未发布，为下一步该库存做准备")
    #disable_low_stock_products("camper")

    print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    #export_gender_split_excel("camper")

    # print("\n🟡 Step: 6️⃣ 获取excel文件用来更新淘宝店铺价格")
    # generate_price_excel(
    #     brand="camper",
    #     input_dir=r"D:\TB\Products\camper\repulibcation\store_prices\input", 
    #     output_path=r"D:\TB\Products\camper\repulibcation\store_prices\camper_channel_prices.xlsx",
    #     drop_rows_without_price=False # 不丢行，查不到的价格留空
    # )

    print("\\n🟡 Step: 6️⃣ 导出库存用于更新")
    # stock_dest_excel_folder = r"D:\TB\Products\camper\repulibcation\stock"
    # export_stock_excel("camper",stock_dest_excel_folder)

    price_dest_excel = r"D:\TB\Products\camper\repulibcation\publication_prices.xlsx"
    export_jiangya_channel_prices("camper",price_dest_excel)



    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    # generate_publication_excels("camper")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    # export_skuid_stock_excel("camper")

    print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    #export_low_stock_for_brand("camper", threshold=5)

    print("\\n🟡 Step: 6️⃣ 导出渠道价格 Excel（含零售价与商家编码），可以用于淘宝店铺去更新商品价格")
    # code_file_path = r"D:\TB\Products\camper\repulibcation\publication_codes.txt"
    # code_missing_path = r"D:\TB\Products\camper\repulibcation\publication_codes_missing.txt"
    # export_channel_price_excel_from_txt("camper",code_file_path)
    # export_channel_price_excel("camper", r"D:\TB\Products\camper\repulibcation\exclude_codes.txt") # 导出价格明细（已发布）
    # export_all_sku_price_excel("camper")  # 导出商家编码价格表（所有商品）


    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
