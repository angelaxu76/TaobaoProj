from config import MARKSANDSPENCER
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier

from channels.jingya.export.export_gender_split_excel import export_gender_split_excel
from channels.jingya.export.generate_publication_excel import generate_publication_excels
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from brands.marksandspencer.collect_product_links import collect_lingerie_links, collect_jacket_links
from brands.marksandspencer.fetch_jacket_info import fetch_jackcet_info
from brands.marksandspencer.fetch_lingerie_info import fetch_lingerie_info
from common_taobao.publication.export_low_stock_products import export_low_stock_for_brand


def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(MARKSANDSPENCER)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    collect_lingerie_links()
    collect_jacket_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    fetch_jackcet_info()
    fetch_lingerie_info()

    # TODO: fetch_jackcet_info / fetch_lingerie_info 尚不支持 links_file 参数，
    #       补抓遗漏商品暂时跳过。如需启用，需先给两个 fetch 函数加 links_file 参数。
    # missing_product_link = r"D:\TB\Products\marksandspencer\publication\missing_product_links.txt"
    # generate_missing_links_for_brand("marksandspencer", missing_product_link)
    # fetch_jackcet_info(links_file=missing_product_link)
    # fetch_lingerie_info(links_file=missing_product_link)

    print("\n🟡 Step: 4️⃣ TXT导入数据库 -----将各个商品的TXT中信息导入到数据库中")
    import_txt_to_db_supplier("marksandspencer")

    # print("\n🟡 Step: 5️⃣ 通过解析鲸芽导出的Excel，将鲸芽侧相关的商品ID和SKU信息导入数据库")
    insert_jingyaid_to_db("marksandspencer")

    # print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("marksandspencer")

    # print("\n🟡 Step: 5️⃣ 找出尺码很少的商品ID，将它所有的尺码都设置成0，并将状态变成未发布，为下一步该库存做准备")
    # disable_low_stock_products("marksandspencer")

    print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    export_gender_split_excel("marksandspencer")



    print("\\n🟡 Step: 6️⃣ 鲸芽侧更新价格和库存------")
    stock_dest_excel_folder = r"D:\TB\Products\marksandspencer\repulibcation\stock"
    export_stock_excel("marksandspencer",stock_dest_excel_folder)

    print("\\n🟡 Step: 6️⃣ 导出价格用于更新")
    price_dest_excel_folder = r"D:\TB\Products\marksandspencer\repulibcation\publication_prices"
    export_jiangya_channel_prices("marksandspencer",price_dest_excel_folder)


    print("\\n🟡 Step: 6️⃣为新品创建excel用于鲸芽侧发布")
    generate_publication_excels("marksandspencer")

    print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    export_low_stock_for_brand("marksandspencer", threshold=5)



    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="marksandspencer",
        input_dir=r"D:\TB\Products\marksandspencer\repulibcation\store_prices\input",
        output_dir=r"D:\TB\Products\marksandspencer\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False  # 不丢行，查不到的价格留空
    )

    print("\n✅ marksandspencer pipeline 完成")

if __name__ == "__main__":
    main()
