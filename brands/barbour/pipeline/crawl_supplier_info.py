# from barbour.supplier.terraces_fetch_info import terraces_fetch_info
from config import BARBOUR
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.barbour.supplier.barbour_get_links import barbour_get_links
from brands.barbour.supplier.barbour_fetch_info import barbour_fetch_info
from brands.barbour.supplier.outdoorandcountry_fetch_info import outdoorandcountry_fetch_info
from brands.barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from brands.barbour.supplier.allweathers_get_links import allweathers_get_links
from brands.barbour.supplier.allweathers_fetch_info import allweathers_fetch_info
from brands.barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
# from brands.barbour.supplier.houseoffraser_new_fetch_info import houseoffraser_fetch_info
from brands.barbour.supplier.houseoffraser_fetch_info import houseoffraser_fetch_info
from brands.barbour.supplier.very_get_links import very_get_links
from brands.barbour.supplier.very_fetch_info import very_fetch_info
from brands.barbour.supplier.terraces_fetch_info import terraces_fetch_info
from brands.barbour.supplier.terraces_get_links import collect_terraces_links
from brands.barbour.supplier.philipmorrisdirect_get_links import philipmorris_get_links
from brands.barbour.supplier.cho_get_links import cho_get_links
from brands.barbour.supplier.cho_fetch_info import cho_fetch_info
from brands.barbour.supplier.philipmorrisdirect_fetch_info import philipmorris_fetch_info
from brands.barbour.tools.move_non_barbour_files import move_non_barbour_files
def barbour_crawl_import_pipleline():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(BARBOUR)


    print("步骤 1：获取商品链接")
    barbour_get_links()
    outdoorandcountry_fetch_and_save_links()
    allweathers_get_links()
    houseoffraser_get_links()
    # very_get_links()
    collect_terraces_links()
    philipmorris_get_links()
    cho_get_links()

    print("步骤 2：抓取商品信息并存为TXT")
    barbour_fetch_info()
    outdoorandcountry_fetch_info(max_workers=1)
    allweathers_fetch_info(7)
    houseoffraser_fetch_info(max_workers=7, headless=False)
    # very_fetch_info(max_workers=15)
    terraces_fetch_info(max_workers=7)
    philipmorris_fetch_info(max_workers=7)
    cho_fetch_info(max_workers=7)

    # # print("步骤 3：move no barbour code file")
    move_non_barbour_files(r"D:\TB\Products\barbour\publication\houseoffraser\TXT",r"D:\TB\Products\barbour\publication\houseoffraser\TXT.bk")
    move_non_barbour_files(r"D:\TB\Products\barbour\publication\cho\TXT",r"D:\TB\Products\barbour\publication\cho\TXT.bk")
    move_non_barbour_files(r"D:\TB\Products\barbour\publication\philipmorris\TXT",r"D:\TB\Products\barbour\publication\philipmorris\TXT.bk")
    move_non_barbour_files(r"D:\TB\Products\barbour\publication\terraces\TXT",r"D:\TB\Products\barbour\publication\terraces\TXT.bk")
    
if __name__ == "__main__":
    barbour_crawl_import_pipleline()
