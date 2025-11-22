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
from common_taobao.publication.export_low_stock_products import export_low_stock_for_brand


def main():


    print("\\n🟡 Step: 6️⃣ 鲸芽侧更新价格和库存------")
    stock_dest_excel_folder = r"D:\TB\Products\geox\repulibcation\stock"
    export_stock_excel("geox",stock_dest_excel_folder)

    print("\\n🟡 Step: 6️⃣ 导出价格用于更新")
    price_dest_excel_folder = r"D:\TB\Products\geox\repulibcation\publication_prices"
    export_jiangya_channel_prices("geox",price_dest_excel_folder)

    print("\\n🟡 Step: 6️⃣为新品创建excel用于鲸芽侧发布")
    generate_publication_excels("geox")

    print("\n🟡 Step: 6️⃣ 输出低库存的商品，准备下架")
    export_low_stock_for_brand("geox", threshold=5)

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="geox",
        input_dir=r"D:\TB\Products\geox\document\store_prices\input",
        output_dir=r"D:\TB\Products\geox\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False,  # 不丢行，查不到的价格留空
        blacklist_excel_file=r"D:\TB\Products\geox\document\store_prices\exclude_product_list.xlsx"
    )

    print("\n✅ GEOX pipeline 完成")

if __name__ == "__main__":
    main()
