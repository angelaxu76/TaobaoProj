from barbour.common.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.common.import_supplier_missing_code_to_Db_offers import run_missing_offers_import
from barbour.common.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product
from barbour.supplier.barbour_get_links import barbour_get_links
from barbour.supplier.barbour_fetch_info import barbour_fetch_info
from barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
from barbour.supplier.allweathers_fetch_info import allweathers_fetch_info
from barbour.supplier.allweathers_get_links import allweathers_get_links
from barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
from barbour.supplier.houseoffraser_fetch_info import houseoffraser_fetch_info
from barbour.supplier.very_fetch_info import very_fetch_info
from barbour.supplier.very_get_links import very_get_links
from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from barbour.supplier.terraces_get_links import collect_terraces_links

from barbour.jingya.insert_jingyaid_to_db_barbour import insert_missing_products_with_zero_stock, insert_jingyaid_to_db
from barbour.jingya.fill_offer_to_barbour_inventory import backfill_barbour_inventory_mapped_only
from barbour.common.fill_supplier_jingya_map import fill_supplier_map


def barbour_database_import_pipleline():
    print("\n🌐 步骤 1：抓取商品链接")
    # barbour
    # barbour_get_links()
    # outdoorandcountry_fetch_and_save_links()
    # allweathers_get_links()5
    # houseoffraser_get_links()
    # very_get_links()
    # collect_terraces_links()

    # Step 1: TODO 将txt中数据导入barbour product中
    # barbour_fetch_info()
    # outdoorandcountry_fetch_info(max_workers=10)
    # allweathers_fetch_info(7)
    # houseoffraser_fetch_info(max_workers=5, headless=False)
    # very_fetch_info()
    # terraces_fetch_info()


    # Step 2: TODO 将txt中数据导入barbour product中
    #batch_import_txt_to_barbour_product("barbour")
    #batch_import_txt_to_barbour_product("outdoorandcountry")
    #batch_import_txt_to_barbour_product("allweathers")
    # batch_import_txt_to_barbour_product("houseoffraser")

    # Step 3: TODO 将各个供货商的库存价格等从txt中数据导入数据库offers
    # import_txt_for_supplier("barbour",False)
    # import_txt_for_supplier("outdoorandcountry",False)
    # import_txt_for_supplier("allweathers",False)
    # import_txt_for_supplier("houseoffraser",False)
    # import_txt_for_supplier("very",False)
    # import_txt_for_supplier("terraces",False)

    # Step 4: TODO 将鲸芽已经发布的产品先填充到barbour inventory表，库存补0，后续在靠真实库存来填充
    insert_missing_products_with_zero_stock("barbour")
    insert_jingyaid_to_db("barbour")

    #Step 6: TODO 根据发布文件填充barbour 鲸芽的map表
    # fill_supplier_map()

    # Step 5: TODO 将barbour product和offers中的价格库存和商品信息回填到barbour inventory表
    backfill_barbour_inventory_mapped_only()

if __name__ == "__main__":
    barbour_database_import_pipleline()
