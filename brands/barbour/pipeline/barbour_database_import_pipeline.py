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
    # Step 4: TODO 将鲸芽已经发布的产品先填充到barbour inventory表，库存补0，后续在靠真实库存来填充
    clear_barbour_inventory()
    insert_missing_products_with_zero_stock("barbour")
    insert_jingyaid_to_db("barbour")



    # print("步骤 6：为发布的商品选择合适的供应商，比如库存充足且价格低的")
    # #Step 4: TODO 根据发布文件填充barbour 鲸芽的map表
    # fill_supplier_map()

    # print("     步骤 6.1：为重点商品强制指定供应商覆盖")
    # xlsx_path = r"D:\TB\Products\barbour\document\barbour_supplier.xlsx"
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=True)
    # apply_barbour_supplier_overrides(xlsx_path,dry_run=False)

    # print("     步骤 6.2：生产发布商品的供应商报表")
    # report_path = export_supplier_stock_price_report(
    #     output_path=r"D:\TB\Products\barbour\publication\barbour_supplier_report.xlsx"
    # )
    # print("诊断报表：", report_path)

    # print("     步骤 6.3：为发布商品低库存的商品重新分配供货商")
    # # 先 dry-run 看建议
    # suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=True)
    # suggestions = reassign_low_stock_suppliers(size_threshold=3, dry_run=False)

    print("步骤 7：根据步骤5中的prduct map表中的供货商，将商品的价格库存等信息回填到barbour inventory表")
    backfill_barbour_inventory_single_supplier()

if __name__ == "__main__":
    barbour_database_import_pipleline()
