from config import ECCO,TAOBAO_STORES,BRAND_CONFIG
from channels.jingya.pricing.generate_discount_price_excel import export_discount_price_with_skuids
from channels.jingya.export.export_skuid_stock import export_skuid_stock_excel
from common.ingest.import_txt_to_db import import_txt_to_db
from channels.jingya.export.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs  # ✅ 新增导入
from brands.ecco.collect_product_links import ecco_get_links
from brands.ecco.legacy.fetch_product_info import ecco_fetch_info
from common.publication.mark_offline_products_from_store_excels import mark_offline_products_from_store_excels
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk, generate_stock_excels_bulk
from channels.jingya.pricing.export_taobao_sku_price_stock_excels import export_shop_sku_price_excels, export_shop_sku_stock_excels
#

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(ECCO)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    ecco_get_links()

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    ecco_fetch_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，并且会解析店铺的淘宝导出的excel文件，并导入skuid")
    import_txt_to_db("ecco")

    print("\n🟡 Step: 6️⃣ 导出SKU基本商品的价格到excel，用于更新淘宝店铺商品价格")
    export_shop_sku_price_excels("ecco", r"D:\TB\Products\ecco\repulibcation\store\output_sku_price", include_all=False)

    # print("\n🟡 Step: 6️⃣ 导出SKU基本商品的库存数量到excel，用于更新淘宝店铺商品库存")
    export_shop_sku_stock_excels("ecco", r"D:\TB\Products\ecco\repulibcation\store\output_sku_stock", include_all=False)

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    export_skuid_stock_excel("ecco")

    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    for store in TAOBAO_STORES:
        export_discount_price_with_skuids("ecco", store)

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    for store in TAOBAO_STORES:
        generate_product_excels(ECCO, store)
        codes = get_publishable_product_codes(ECCO, store)
        copy_images_for_store(ECCO, store, codes)


    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="ecco",
        input_dir=r"D:\TB\Products\ecco\repulibcation\store\input",
        output_dir=r"D:\TB\Products\ecco\repulibcation\store\price_output",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False  # 不丢行，查不到的价格留空
    )
    

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺库存，输入文件夹可以是多个店铺的导出文件")
    generate_stock_excels_bulk(
        brand="ecco",
        input_dir=r"D:\TB\Products\ecco\repulibcation\store\input",
        output_dir=r"D:\TB\Products\ecco\repulibcation\store\stock_output",
        suffix="_库存",
        in_stock_qty=3,       # 有货时写入的库存数量
        out_stock_qty=0       # 无货时写入的库存数量
    )

    mark_offline_products_from_store_excels(BRAND_CONFIG["ecco"])
    print("\n✅ ECCO pipeline 完成")

if __name__ == "__main__":
    main()
