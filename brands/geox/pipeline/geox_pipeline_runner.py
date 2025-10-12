import os
import subprocess
from config import GEOX,TAOBAO_STORES,BRAND_CONFIG
from pathlib import Path
from common_taobao.generate_discount_price_excel import export_price_with_itemid,export_store_discount_price
from common_taobao.export_skuid_stock import export_skuid_stock_excel
from common_taobao.import_txt_to_db import import_txt_to_db
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.generate_discount_price_excel import export_store_discount_price,export_discount_price_with_skuids
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from common_taobao.mark_offline_products_from_store_excels import mark_offline_products_from_store_excels
from brands.geox.core.unified_link_collector import collect_all_product_links
from brands.clarks_Jingya.unified_link_collector import generate_product_links
from brands.clarks_Jingya.clarks_jinya_fetch_product_info import clarks_fetch_info
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel
from common_taobao.jingya.jingya_export_stockcount_to_excel import export_stock_excel
from common_taobao.jingya.jiangya_export_channel_price_excel import export_jiangya_channel_prices
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_channel_price_excel_from_txt,export_channel_price_excel_from_channel_ids

# from brands.geox.core.fetch_product_info import fetch_all_product_info

from brands.geox.core.geox_jingya_fetch_product_info import fetch_all_product_info

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    # print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    # backup_and_clear_brand_dirs(GEOX)

    # print("\n🟡 Step: 2️⃣ 抓取商品链接")
    # collect_all_product_links()

    # print("\n🟡 Step: 3️⃣ 抓取商品信息")
    # fetch_all_product_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    import_txt_to_db_supplier("geox")  # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    insert_jingyaid_to_db("geox")

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("geox")

if __name__ == "__main__":
    main()
