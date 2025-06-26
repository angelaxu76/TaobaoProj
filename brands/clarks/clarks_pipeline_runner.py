import os
import shutil
import subprocess
from datetime import datetime
from config import CLARKS
from common_taobao.generate_discount_price_excel import export_store_discount_price
from common_taobao.export_skuid_stock import export_skuid_stock_excel
from common_taobao.import_txt_to_db import import_txt_to_db
from common_taobao.prepare_utils_extended import generate_product_excels, copy_images_for_store, get_publishable_product_codes
from pathlib import Path

BASE_DIR = CLARKS["BASE"]
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
    print("\n🟡 Step: 1️⃣ 清空发布目录")
    if REPUB_DIR.exists():
        store_list = [folder.name for folder in REPUB_DIR.iterdir() if folder.is_dir()]
        #  for store in store_list:
        #   backup_and_clear_dir(REPUB_DIR / store, f"repulibcation/{store}")
    else:
        print(f"⚠️ 发布目录不存在: {REPUB_DIR}，跳过")

    print("\n🟡 Step: 2️⃣ 抓取商品链接")

    # run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
    run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库")
    import_txt_to_db("clarks")

    print("\n🟡 Step: 5️⃣ 导出价格 Excel")
    export_store_discount_price("clarks")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    export_skuid_stock_excel("clarks")

    print("\n🟡 Step: 7️⃣ 为各店铺生成上架 Excel + 拷贝图片")
    # 手动指定调试店铺
    store_list = ["五小剑", "英国伦敦代购2015"]
    for store in store_list:
        generate_product_excels(CLARKS, store)
        codes = get_publishable_product_codes(CLARKS, store)
        copy_images_for_store(CLARKS, store, codes)

    print("\n✅ Clarks pipeline 完成")

if __name__ == "__main__":
    main()