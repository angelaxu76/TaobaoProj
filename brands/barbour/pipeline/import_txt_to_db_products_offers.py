# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from brands.barbour.common.import_txt_to_products_v2 import batch_import_txt_to_barbour_product
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import insert_jingyaid_to_db,clear_barbour_inventory,insert_missing_products_with_zero_stock
from brands.barbour.common.build_supplier_jingya_mapping import fill_supplier_map,apply_barbour_supplier_overrides,export_supplier_stock_price_report,reassign_low_stock_suppliers
from brands.barbour.jingya.merge_offer_into_inventory import backfill_barbour_inventory_single_supplier

def barbour_database_import_pipleline():


    print("步骤 3：将txt中数据导入barbour product中")
    batch_import_txt_to_barbour_product("barbour")
    batch_import_txt_to_barbour_product("outdoorandcountry")
    batch_import_txt_to_barbour_product("allweathers")
    batch_import_txt_to_barbour_product("philipmorris")
    batch_import_txt_to_barbour_product("cho")

    # batch_import_txt_to_barbour_product("houseoffraser")

    print("步骤 4：将txt中数据导入barbour offers中，成为可以供应的仓库")
    import_txt_for_supplier("barbour",False)
    import_txt_for_supplier("outdoorandcountry",False)
    import_txt_for_supplier("allweathers",False)
    import_txt_for_supplier("houseoffraser",False)
    import_txt_for_supplier("very",False)
    import_txt_for_supplier("terraces",False)
    import_txt_for_supplier("philipmorris",False)
    import_txt_for_supplier("cho",False)
    
if __name__ == "__main__":
    barbour_database_import_pipleline()
