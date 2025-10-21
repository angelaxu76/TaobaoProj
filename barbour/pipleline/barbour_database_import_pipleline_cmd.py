from barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.common.import_supplier_missing_code_to_Db_offers import run_missing_offers_import
from barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from barbour.supplier.barbour_get_links import barbour_get_links
from barbour.supplier.barbour_fetch_info import barbour_fetch_info
from barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
from barbour.supplier.allweathers_fetch_info import allweathers_fetch_info
from barbour.supplier.allweathers_get_links import allweathers_get_links
from barbour.supplier.houseoffraser_new_fetch_info import houseoffraser_fetch_info
from barbour.supplier.very_fetch_info import very_fetch_info
from barbour.supplier.very_get_links import very_get_links
from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from barbour.supplier.terraces_get_links import collect_terraces_links
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from barbour.jingya.insert_jingyaid_to_db_barbour import insert_missing_products_with_zero_stock, insert_jingyaid_to_db, clear_barbour_inventory
from barbour.jingya.fill_offer_to_barbour_inventory import backfill_barbour_inventory_mapped_only,backfill_barbour_inventory_single_supplier
from barbour.common.fill_supplier_jingya_map import fill_supplier_map,export_supplier_stock_price_report,reassign_low_stock_suppliers
from common_taobao.jingya.jingya_export_stockcount_to_excel import export_stock_excel
from common_taobao.jingya.jiangya_export_channel_price_excel import export_barbour_channel_price_by_sku,export_jiangya_channel_prices
from common_taobao.generate_taobao_store_price_for_import_excel import generate_price_excel,generate_price_excels_bulk
from config import BARBOUR


def barbour_database_import_pipleline():
    # print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(BARBOUR)


    print("\n🌐 步骤 1：抓取商品链接")
    # barbour
    # barbour_get_links()
    # outdoorandcountry_fetch_and_save_links()
    # allweathers_get_links()
    # houseoffraser_fetch_info()
    # very_get_links()
    # collect_terraces_links()

    # Step 1: TODO 将txt中数据导入barbour product中
    # barbour_fetch_info()
    # outdoorandcountry_fetch_info(max_workers=10)
    # allweathers_fetch_info(7)
    # houseoffraser_fetch_info(max_workers=1, headless=False)
    # very_fetch_info()
    # terraces_fetch_info()


    # Step 2: TODO 将txt中数据导入barbour product中
    #batch_import_txt_to_barbour_product("barbour")
    #batch_import_txt_to_barbour_product("outdoorandcountry")
    #batch_import_txt_to_barbour_product("allweathers")
    # batch_import_txt_to_barbour_product("houseoffraser")
    # batch_import_txt_to_barbour_product("houseoffraser")

    # Step 3: TODO 将各个供货商的库存价格等从txt中数据导入数据库offers
    # import_txt_for_supplier("barbour",False)
    # import_txt_for_supplier("outdoorandcountry",False)
    # import_txt_for_supplier("allweathers",False)
    # import_txt_for_supplier("houseoffraser",False)
    # import_txt_for_supplier("very",False)
    # import_txt_for_supplier("terraces",False)

    # Step 4: TODO 将鲸芽已经发布的产品先填充到barbour inventory表，库存补0，后续在靠真实库存来填充
    # clear_barbour_inventory()
    # insert_missing_products_with_zero_stock("barbour")
    # insert_jingyaid_to_db("barbour")

    #Step 6: TODO 根据发布文件填充barbour 鲸芽的map表
    # fill_supplier_map()

    # 2.2 可选：导出“各站点库存与价格”诊断报表（便于检查当前映射与最佳站点差异）
    # report_path = export_supplier_stock_price_report(
    #     output_path=r"D:\TB\Products\barbour\publication\barbour_supplier_report.xlsx"
    # )
    # print("诊断报表：", report_path) 


    # 2.3 可选：根据尺码阈值（默认3）自动建议/切换到“有货尺码≥3且最低价”的站点
    # 先 dry-run 看建议
    # suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=True)

    #suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=False)



    # Step 5: TODO 将barbour product和offers中的价格库存和商品信息回填到barbour inventory表
    # backfill_barbour_inventory_single_supplier()


    # print("\\n🟡 Step: 6️⃣鲸芽 导出库存用于更新")
    # stock_dest_excel_folder = r"D:\TB\Products\barbour\repulibcation\stock"
    # export_stock_excel("barbour",stock_dest_excel_folder)

    # print("\\n🟡 Step: 6️⃣鲸芽 导出价格用于更新")
    # price_dest_excel = r"D:\TB\Products\barbour\repulibcation\publication_prices"
    # export_jiangya_channel_prices("barbour",price_dest_excel)

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="barbour",
        input_dir=r"D:\TB\Products\barbour\repulibcation\store_prices\input",
        output_dir=r"D:\TB\Products\barbour\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False  # 不丢行，查不到的价格留空
    )


    # print("\\n🟡 Step: 6️⃣ 导出barbour sku基本价格用于更新鲸芽价格")
    # export_barbour_channel_price_by_sku(
    # brand="barbour",
    # output_dir=r"D:\TB\Products\barbour\repulibcation\price",
    # strict=False,
    # chunk_size=200   # 用的是默认值
    # )


if __name__ == "__main__":
    barbour_database_import_pipleline()
