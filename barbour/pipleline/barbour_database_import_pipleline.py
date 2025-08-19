from pathlib import Path
from barbour.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.barbour_import_to_barbour_products import batch_import_txt_to_barbour_product

def barbour_database_import_pipleline():
    # Step 1: TODO 将txt中数据导入barbour product中
    batch_import_txt_to_barbour_product()

    # Step 2: TODO 将各个供货商的库存价格等从txt中数据导入数据库offers
    #import_txt_for_supplier("allweathers")



if __name__ == "__main__":
    barbour_database_import_pipleline()