# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.supplier.barbour_get_links import barbour_get_links
from brands.barbour.supplier.barbour_fetch_info import barbour_fetch_info
from brands.barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
from brands.barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from brands.barbour.supplier.allweathers_get_links import allweathers_get_links
from brands.barbour.supplier.allweathers_fetch_info import allweathers_fetch_info
from brands.barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
# from brands.barbour.supplier.houseoffraser_new_fetch_info import houseoffraser_fetch_info
from brands.barbour.supplier.houseoffraser_new_fetch_info_v3 import houseoffraser_fetch_info
from brands.barbour.supplier.very_get_links import very_get_links
from brands.barbour.supplier.very_fetch_info import very_fetch_info
from brands.barbour.supplier.terraces_fetch_info import terraces_fetch_info
from brands.barbour.supplier.terraces_get_links import collect_terraces_links
from brands.barbour.supplier.philipmorrisdirect_get_links import philipmorris_get_links
from brands.barbour.supplier.cho_get_links import cho_get_links
from brands.barbour.supplier.cho_fetch_info import cho_fetch_info
from brands.barbour.supplier.philipmorrisdirect_fetch_info import philipmorris_fetch_info
from brands.barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from brands.barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from brands.barbour.jingya.insert_jingyaid_mapping import insert_jingyaid_to_db,clear_barbour_inventory,insert_missing_products_with_zero_stock
from brands.barbour.common.fill_supplier_jingya_map import fill_supplier_map,apply_barbour_supplier_overrides,export_supplier_stock_price_report,reassign_low_stock_suppliers
from brands.barbour.jingya.merge_offer_into_inventory import backfill_barbour_inventory_single_supplier

def barbour_database_import_pipleline():
    # print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(BARBOUR)


    print("步骤 1：获取商品链接")
    # barbour_get_links()
    # outdoorandcountry_fetch_and_save_links()
    # allweathers_get_links()
    # houseoffraser_get_links()
    # very_get_links()
    # collect_terraces_links()
    # philipmorris_get_links()
    # cho_get_links()

    print("步骤 2：抓取商品信息并存为TXT")
    # barbour_fetch_info()
    # outdoorandcountry_fetch_info(max_workers=15)
    # allweathers_fetch_info(7)
    houseoffraser_fetch_info(max_workers=15, headless=False)
    # very_fetch_info(max_workers=15)
    # terraces_fetch_info(max_workers=15)
    # philipmorris_fetch_info(max_workers=15)
    # cho_fetch_info(max_workers=15)


    
if __name__ == "__main__":
    barbour_database_import_pipleline()
