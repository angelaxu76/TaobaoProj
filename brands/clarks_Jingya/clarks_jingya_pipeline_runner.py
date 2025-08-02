import os
import shutil
import subprocess
from datetime import datetime
from config import CLARKS_JINGYA,TAOBAO_STORES,BRAND_CONFIG
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_all_sku_price_excel
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from common_taobao.jingya.import_txt_to_db_supplier import import_txt_to_db_supplier
from common_taobao.jingya.disable_low_stock_product import disable_low_stock_products
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel
from common_taobao.generate_discount_price_excel import export_store_discount_price
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from pathlib import Path

BASE_DIR = CLARKS_JINGYA["BASE"]
PUBLICATION_DIR = BASE_DIR / "publication"
REPUB_DIR = BASE_DIR / "repulibcation"
BACKUP_DIR = BASE_DIR / "backup"

def backup_and_clear_dir(dir_path: Path, name: str):
    if not dir_path.exists():
        print(f"⚠️ 目录不存在: {dir_path}，跳过")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / timestamp / name
    shutil.copytree(dir_path, backup_path)
    print(f"📦 已备份: {dir_path} → {backup_path}")
    for item in dir_path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    print(f"🧹 已清空目录: {name}")

def run_script(filename: str):
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path], check=True)

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    #backup_and_clear_brand_dirs(CLARKS_JINGYA)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    #generate_product_links("clarks_jingya")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    #import_txt_to_db_supplier("clarks_jingya")  # ✅ 新逻辑


    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    #for store in TAOBAO_STORES:
     #export_discount_price_with_skuids("clarks",store)

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    #export_skuid_stock_excel("clarks")

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    # 手动指定调试店铺

    #for store in TAOBAO_STORES:
    #  generate_product_excels(CLARKS_JINGYA, store)
    #  codes = get_publishable_product_codes(CLARKS_JINGYA, store)
    #   copy_images_for_store(CLARKS_JINGYA, store, codes)

    # 导出需要下架的产品
    #mark_offline_products_from_store_excels(BRAND_CONFIG["clarks"])
    print("\n✅ Clarks pipeline 完成")

if __name__ == "__main__":
    main()