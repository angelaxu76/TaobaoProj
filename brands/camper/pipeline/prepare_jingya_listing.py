from config import CAMPER
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.maintenance.disable_low_stock_products import disable_low_stock_products
from channels.jingya.export.export_gender_split_excel import export_gender_split_excel
from channels.jingya.export.generate_publication_excel import generate_publication_excels
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from brands.camper.fetch_product_info_v2 import camper_fetch_product_info
from brands.camper.collect_product_links import camper_get_links
from common_taobao.publication.export_low_stock_products import export_low_stock_for_brand
from common_taobao.core.generate_missing_links_for_brand import generate_missing_links_for_brand

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CAMPER)

    # print("\n🟡 Step: 2️⃣ 抓取商品链接")
    camper_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    camper_fetch_product_info()



    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\camper\publication\missing_product_links.txt";
    generate_missing_links_for_brand("camper",missing_product_link )
    camper_fetch_product_info(links_file=missing_product_link )

    print("\n🟡 Step: 4️⃣ TXT导入数据库 -----将各个商品的TXT中信息导入到数据库中")
    import_txt_to_db_supplier("camper",exchange_rate=9.4,delivery_cost=7)  

    print("\n🟡 Step: 5️⃣ 通过解析鲸芽导出的Excel，将鲸芽侧相关的商品ID和SKU信息导入数据库")
    insert_jingyaid_to_db("camper")

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("camper")

    print("\n🟡 Step: 5️⃣ 找出尺码很少的商品ID，将它所有的尺码都设置成0，并将状态变成未发布，为下一步该库存做准备")
    # disable_low_stock_products("camper")

    print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    export_gender_split_excel("camper")



    print("\\n🟡 Step: 6️⃣ 鲸芽侧更新价格和库存------")
    stock_dest_excel_folder = r"D:\TB\Products\camper\repulibcation\stock"
    export_stock_excel("camper",stock_dest_excel_folder)

    print("\\n🟡 Step: 6️⃣ 导出价格用于更新")
    price_dest_excel_folder = r"D:\TB\Products\camper\repulibcation\publication_prices"
    export_jiangya_channel_prices("camper",price_dest_excel_folder,chunk_size=300,exchange_rate=9.4)


    print("\\n🟡 Step: 6️⃣为新品创建excel用于鲸芽侧发布")
    generate_publication_excels("camper")

    print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    export_low_stock_for_brand("camper", threshold=5)



    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="camper",
        input_dir=r"D:\TB\Products\camper\document\store_prices",
        output_dir=r"D:\TB\Products\camper\repulibcation\store_prices",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False,
        blacklist_excel_file=r"D:\TB\Products\camper\document\camper_blacklist_excel.xlsx" # 不丢行，查不到的价格留空
    )

    print("\n✅ CAMPER pipeline 完成")

if __name__ == "__main__":
    main()
