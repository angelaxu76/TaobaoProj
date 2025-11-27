# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import insert_jingyaid_to_db,clear_barbour_inventory,insert_missing_products_with_zero_stock
from brands.barbour.common.fill_supplier_jingya_map import fill_supplier_map,apply_barbour_supplier_overrides,export_supplier_stock_price_report,reassign_low_stock_suppliers
from brands.barbour.jingya.merge_offer_into_inventory import backfill_barbour_inventory_single_supplier

def barbour_database_import_pipleline():


    print("步骤 5：将barbour inventory清空，并重新填充已发布商品信息，通过jingya id导出的excel文件")


    # 常规场景1: TODO 获取供货商新的库存和价格后，更新数据库
    # clear_barbour_inventory()
    # insert_missing_products_with_zero_stock("barbour")
    # insert_jingyaid_to_db("barbour")
    # backfill_barbour_inventory_single_supplier()



    # 常规场景2: TODO 在鲸芽发布了新的商品后，为新的商品绑定供货商，并更新和设置所有商品的库存和价格
    # clear_barbour_inventory()
    # insert_missing_products_with_zero_stock("barbour")
    # insert_jingyaid_to_db("barbour")
    # fill_supplier_map(force_refresh=False, exclude_xlsx=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx")
    # backfill_barbour_inventory_single_supplier()


    # 常规场景3: TODO 数据库全部清空后需要重新填充数据。
    # clear_barbour_inventory()
    # insert_missing_products_with_zero_stock("barbour")
    # insert_jingyaid_to_db("barbour")

    xlsx_path = r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=True)
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=False)

    fill_supplier_map(force_refresh=False, exclude_xlsx=xlsx_path)
    backfill_barbour_inventory_single_supplier()



    # 常规场景4: TODO 为低库存的商品重新分配供货商，并更新和设置所有商品的库存和价格
    # 仅预览建议，不改库，同时跳过排除清单中列出的编码
    # reassign_low_stock_suppliers(
    #     size_threshold=3,
    #     dry_run=True,
    #     exclude_xlsx=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
    # )

    # 确认后执行真更新（会更新 map，但仍跳过排除清单中的编码）
    # reassign_low_stock_suppliers(
    #     size_threshold=3,
    #     dry_run=False,
    #     exclude_xlsx=r"D:\TB\Products\barbour\document\barbour_exclude_list.xlsx"
    # )

    # 更新map后，在重新更新barbour inventory
    # clear_barbour_inventory()
    # insert_missing_products_with_zero_stock("barbour")
    # insert_jingyaid_to_db("barbour")
    # backfill_barbour_inventory_single_supplier()






   

    # print("     步骤 6.1：为重点商品强制指定供应商覆盖")
    xlsx_path = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=True)
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=False)

    # print("     步骤 6.2：生产发布商品的供应商报表")
    # report_path = export_supplier_stock_price_report(
    #     output_path=r"D:\TB\Products\barbour\publication\barbour_supplier_report.xlsx"
    # )
    # print("诊断报表：", report_path)



if __name__ == "__main__":
    barbour_database_import_pipleline()
