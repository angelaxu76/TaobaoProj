import os
import subprocess
from config import GEOX
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.geox.collect_product_links import collect_all_product_links
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.export.generate_publication_excel import generate_publication_excels
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.core.generate_missing_links_for_brand import generate_missing_links_for_brand

# from brands.geox.core.fetch_product_info import fetch_all_product_info

from brands.geox.fetch_product_info_jingya import fetch_all_product_info

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(GEOX)

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    collect_all_product_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    fetch_all_product_info()

    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\geox\publication\missing_product_links.txt";
    generate_missing_links_for_brand("geox",missing_product_link )
    fetch_all_product_info(missing_product_link )



    # print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    # import_txt_to_db_supplier("geox")  # ✅ 新逻辑

    # print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    # insert_jingyaid_to_db("geox")

    # print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    # insert_missing_products_with_zero_stock("geox")


    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    generate_publication_excels("geox")

    print("\\n🟡 Step: 6️⃣ 导出库存用于更新")
    stock_dest_excel_folder = r"D:\TB\Products\geox\repulibcation\stock"
    export_stock_excel("geox",stock_dest_excel_folder)

    print("\\n🟡 Step: 6️⃣ 导出价格用于更新")
    price_dest_excel = r"D:\TB\Products\geox\repulibcation\publication_prices"
    exclude_exccel = r"D:\TB\Products\geox\document\exclude.xlsx"
    export_jiangya_channel_prices("geox",price_dest_excel,exclude_exccel)

if __name__ == "__main__":
    main()
