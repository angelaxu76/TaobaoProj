from config import CAMPER
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from channels.jingya.maintenance.disable_low_stock_products import disable_low_stock_products
from channels.jingya.export.export_gender_split_excel import export_gender_split_excel
from channels.jingya.export.generate_publication_excel_v2 import generate_publication_excels
from channels.jingya.pricing.generate_discount_excel_for_taobao import generate_discount_excel
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_for_brand


def main():


    # print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    # export_gender_split_excel("camper")

    # print("\\n🟡 Step: 6️⃣ 鲸芽侧更新价格和库存------")
    # stock_dest_excel_folder = r"D:\TB\Products\camper\repulibcation\stock"
    # export_stock_excel("camper",stock_dest_excel_folder)

    # print("\\n🟡 Step: 6️⃣ 导出价格用于更新")
    # price_dest_excel_folder = r"D:\TB\Products\camper\repulibcation\publication_prices"
    # export_jiangya_channel_prices("camper",price_dest_excel_folder)


    print("\\n🟡 Step: 6️⃣为新品创建excel用于鲸芽侧发布")
    generate_publication_excels("camper")

    # print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    # export_low_stock_for_brand("camper", threshold=5)



    # print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    # generate_price_excels_bulk(
    #     brand="camper",
    #     input_dir=r"D:\TB\Products\camper\document\store_prices",
    #     output_dir=r"D:\TB\Products\camper\repulibcation\store_prices\output",
    #     suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
    #     drop_rows_without_price=False,
    #     blacklist_excel_file=r"D:\TB\Products\camper\document\camper_blacklist_excel.xlsx" # 不丢行，查不到的价格留空
    # )


    # generate_discount_excel(
    # brand="camper",
    # output_excel_path=r"D:\TB\Products\camper\repulibcation\camper_discount_export.xlsx",
    # blacklist_excel_file=r"D:\TB\Products\camper\document\camper_blacklist_excel.xlsx"
    # )

    # print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
