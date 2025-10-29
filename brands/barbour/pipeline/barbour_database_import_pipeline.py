# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_barbour_channel_price_by_sku,export_jiangya_channel_prices
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.supplier.barbour_get_links import barbour_get_links
from brands.barbour.supplier.barbour_fetch_info import barbour_fetch_info
from brands.barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
from brands.barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from brands.barbour.supplier.allweathers_get_links import allweathers_get_links
from brands.barbour.supplier.allweathers_fetch_info import allweathers_fetch_info
from brands.barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
from brands.barbour.supplier.houseoffraser_new_fetch_info import houseoffraser_fetch_info
from brands.barbour.supplier.very_get_links import very_get_links
from brands.barbour.supplier.very_fetch_info import very_fetch_info
from brands.barbour.supplier.terraces_fetch_info import terraces_fetch_info
from brands.barbour.supplier.terraces_get_links import collect_terraces_links
from brands.barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import insert_jingyaid_to_db,clear_barbour_inventory,insert_missing_products_with_zero_stock
from brands.barbour.common.fill_supplier_jingya_map import fill_supplier_map,apply_barbour_supplier_overrides,export_supplier_stock_price_report,reassign_low_stock_suppliers
from brands.barbour.jingya.merge_offer_into_inventory import backfill_barbour_inventory_single_supplier

def barbour_database_import_pipleline():
    # print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(BARBOUR)


    print("步骤 1：获取商品链接")
    barbour_get_links()
    outdoorandcountry_fetch_and_save_links()
    allweathers_get_links()
    houseoffraser_get_links()
    very_get_links()
    collect_terraces_links()

    print("步骤 2：抓取商品信息并存为TXT")
    barbour_fetch_info()
    outdoorandcountry_fetch_info(max_workers=10)
    allweathers_fetch_info(7)
    houseoffraser_fetch_info(max_workers=1, headless=False)
    very_fetch_info()
    terraces_fetch_info()


    print("步骤 3：将txt中数据导入barbour product中")
    batch_import_txt_to_barbour_product("barbour")
    batch_import_txt_to_barbour_product("outdoorandcountry")
    batch_import_txt_to_barbour_product("allweathers")
    batch_import_txt_to_barbour_product("houseoffraser")
    batch_import_txt_to_barbour_product("houseoffraser")

    print("步骤 4：将txt中数据导入barbour offers中，成为可以供应的仓库")
    import_txt_for_supplier("barbour",False)
    import_txt_for_supplier("outdoorandcountry",False)
    import_txt_for_supplier("allweathers",False)
    import_txt_for_supplier("houseoffraser",False)
    import_txt_for_supplier("very",False)
    import_txt_for_supplier("terraces",False)



    print("步骤 5：将barbour inventory清空，并重新填充已发布商品信息，通过jingya id导出的excel文件")
    # Step 4: TODO 将鲸芽已经发布的产品先填充到barbour inventory表，库存补0，后续在靠真实库存来填充
    clear_barbour_inventory()
    insert_missing_products_with_zero_stock("barbour")
    insert_jingyaid_to_db("barbour")



    print("步骤 6：为发布的商品选择合适的供应商，比如库存充足且价格低的")
    #Step 4: TODO 根据发布文件填充barbour 鲸芽的map表
    fill_supplier_map()

    print("     步骤 6.1：为重点商品强制指定供应商覆盖")
    xlsx_path = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"
    apply_barbour_supplier_overrides(xlsx_path,dry_run=True)
    apply_barbour_supplier_overrides(xlsx_path,dry_run=False)

    print("     步骤 6.2：生产发布商品的供应商报表")
    report_path = export_supplier_stock_price_report(
        output_path=r"D:\TB\Products\barbour\publication\barbour_supplier_report.xlsx"
    )
    print("诊断报表：", report_path)

    print("     步骤 6.3：为发布商品低库存的商品重新分配供货商")
    # 先 dry-run 看建议
    suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=True)
    suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=False)

    

    print("步骤 7：根据步骤5中的prduct map表中的供货商，将商品的价格库存等信息回填到barbour inventory表")
    backfill_barbour_inventory_single_supplier()



    ######################################################################
    ################导出EXCEL 用于更新鲸芽和淘宝##########################
    ######################################################################


    print("导出excel 用于更新鲸芽库存")
    stock_dest_excel_folder = r"D:\TB\Products\barbour\repulibcation\stock"
    export_stock_excel("barbour",stock_dest_excel_folder)
    
    print("导出excel 用于更新鲸芽价格=====商品级别"    )
    price_dest_excel_path = r"D:\TB\Products\barbour\repulibcation\publication_prices"
    xlsx_path = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"

    export_jiangya_channel_prices(
    brand="barbour",
    output_dir=price_dest_excel_path,
    exclude_excel_file=xlsx_path
    )

    print("导出excel 用于更新鲸芽价格=====SKU级别"    )
    export_barbour_channel_price_by_sku(
    brand="barbour",
    output_excel_path=r"D:\TB\Products\barbour\repulibcation\publication_sku_prices\sku_level_prices",
    exclude_excel_file=xlsx_path,
    chunk_size=200   # 用的是默认值
    )

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    xlsx_path = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"
    generate_price_excels_bulk(
        brand="barbour",
        input_dir=r"D:\TB\Products\barbour\repulibcation\store_prices\input",
        output_dir=r"D:\TB\Products\barbour\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀
        drop_rows_without_price=False,  # 查不到的价格留空（你可以改成 True 表示丢掉无价的）
        blacklist_excel_file=xlsx_path  # ✅ 新增参数：传入黑名单文件
    )

if __name__ == "__main__":
    barbour_database_import_pipleline()
