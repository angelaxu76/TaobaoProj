from research.import_store_products_to_db import import_store_products_to_db
from research.update_sycm_to_db import update_sycm_data


def main():
    import_store_products_to_db(r"D:\TB\Products\all")

    #update_sycm_data("D:/TB/Products/all/sycm")

if __name__ == "__main__":
    main()