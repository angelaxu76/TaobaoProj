# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_channel_price_by_sku,export_jiangya_channel_prices
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import insert_jingyaid_to_db,clear_barbour_inventory,insert_missing_products_with_zero_stock
from brands.barbour.common.fill_supplier_jingya_map import fill_supplier_map,apply_barbour_supplier_overrides,export_supplier_stock_price_report,reassign_low_stock_suppliers
from brands.barbour.jingya.merge_offer_into_inventory import backfill_barbour_inventory_single_supplier

def barbour_export_price_stock():

    exclude_xlsx_path = r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
    ######################################################################
    ################导出EXCEL 用于更新鲸芽和淘宝##########################
    ######################################################################


    # print("导出excel 用于更新鲸芽库存")
    # stock_dest_excel_folder = r"D:\TB\Products\barbour\repulibcation\stock"
    # export_stock_excel("barbour",stock_dest_excel_folder)
    
    # print("导出excel 用于更新鲸芽价格=====商品级别"    )
    # price_dest_excel_path = r"D:\TB\Products\barbour\repulibcation\publication_prices"
    # export_jiangya_channel_prices(
    # brand="barbour",
    # output_dir=price_dest_excel_path,
    # exclude_excel_file=exclude_xlsx_path
    # )

    # print("导出excel 用于更新鲸芽价格=====SKU级别"    )
    # export_channel_price_by_sku(
    # brand="barbour",
    # output_excel_path=r"D:\TB\Products\barbour\repulibcation\publication_sku_prices\sku_level_prices",
    # exclude_excel_file=exclude_xlsx_path,
    # chunk_size=200   # 用的是默认值
    # )

    # export_channel_price_by_sku(
    # brand="barbour",
    # output_excel_path=r"D:\TB\Products\barbour\repulibcation\publication_sku_prices\sku_level_prices",
    # exclude_excel_file=exclude_xlsx_path,
    # chunk_size=200   # 用的是默认值
    # filter_txt_file=r"D:\TB\Products\barbour\document\only_these_channel_ids.txt"  # ← 新增
    # )

    print("\n🟡 Step: 6️⃣ 获取excel文件，用来更新各个淘宝店铺价格，输入文件夹可以是多个店铺的导出文件")
    generate_price_excels_bulk(
        brand="barbour",
        input_dir=r"D:\TB\Products\barbour\document\store",
        output_dir=r"D:\TB\Products\barbour\repulibcation\store_prices\output",
        suffix="_价格",                # 输出文件后缀
        drop_rows_without_price=False,  # 查不到的价格留空（你可以改成 True 表示丢掉无价的）
        blacklist_excel_file=exclude_xlsx_path  # ✅ 新增参数：传入黑名单文件
    )

if __name__ == "__main__":
    barbour_export_price_stock()
