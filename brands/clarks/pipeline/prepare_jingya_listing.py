import os
import subprocess
from config import CLARKS
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.clarks.collect_product_links import generate_product_links
from brands.clarks.fetch_product_info import clarks_fetch_info
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.export.generate_publication_excel_shoes import generate_publication_excels
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand

# def run_script(filename: str):
#     path = os.path.join(os.path.dirname(__file__), filename)
#     print(f"⚙️ 执行脚本: {filename}")
#     subprocess.run(["python", path], check=True)

def main():
    code_file_path = r"D:\TB\Products\clarks\repulibcation\publication_codes.txt"
    
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CLARKS)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接") 
    generate_product_links("clarks")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    clarks_fetch_info()

    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\clarks\publication\missing_product_links.txt"
    generate_missing_links_for_brand("clarks", missing_product_link)
    if os.path.exists(missing_product_link):
        clarks_fetch_info(missing_product_link)


    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    import_txt_to_db_supplier("clarks",exchange_rate=9.4,delivery_cost=7)    # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    insert_jingyaid_to_db("clarks", debug=True)

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("clarks")


    print("\n🟡 Step: 6️⃣ 获取excel文件用来更新淘宝店铺价格")
    generate_price_excels_bulk(
        brand="clarks",
        input_dir=r"D:\TB\Products\clarks\repulibcation\store_prices\input",
        output_dir=r"D:\TB\Products\clarks\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False  # 不丢行，查不到的价格留空
    )

    generate_price_excels_bulk(
        brand="clarks",
        input_dir=r"D:\TB\Products\clarks\document\store_prices",
        output_dir=r"D:\TB\Products\clarks\repulibcation\store_prices",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False,
        blacklist_excel_file=r"D:\TB\Products\clarks\document\exclude.xlsx" # 不丢行，查不到的价格留空
    )


    print("\\n🟡 Step: 6️⃣ 导出库存用于更新")
    stock_dest_excel_folder = r"D:\TB\Products\clarks\repulibcation\stock"
    export_stock_excel("clarks",stock_dest_excel_folder)

    price_dest_excel = r"D:\TB\Products\clarks\repulibcation\publication_prices"
    export_jiangya_channel_prices("clarks",price_dest_excel,chunk_size=200)

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    generate_publication_excels("clarks")

if __name__ == "__main__":
    main()