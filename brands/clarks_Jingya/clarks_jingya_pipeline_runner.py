import os
import shutil
import subprocess
from datetime import datetime
from config import CLARKS_JINGYA,TAOBAO_STORES,BRAND_CONFIG
from common_taobao.jingya.import_channel_info_from_excel import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel,export_channel_price_excel_from_txt
from common_taobao.backup_and_clear import backup_and_clear_brand_dirs
from brands.clarks_Jingya.unified_link_collector import generate_product_links
from brands.clarks_Jingya.clarks_jinya_fetch_product_info import clarks_fetch_info
from common_taobao.jingya.jingya_import_txt_to_db import import_txt_to_db_supplier
from common_taobao.jingya.generate_publication_excel import generate_publication_excels
from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel

from pathlib import Path

BASE_DIR = CLARKS_JINGYA["BASE"]
PUBLICATION_DIR = BASE_DIR / "publication"
REPUB_DIR = BASE_DIR / "repulibcation"
BACKUP_DIR = BASE_DIR / "backup"

######################################
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
    code_file_path = r"D:\TB\Products\clarks_jingya\repulibcation\publication_codes.txt"
    
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    ##backup_and_clear_brand_dirs(CLARKS_JINGYA)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    ##generate_product_links("clarks_jingya")

    print("\n🟡 Step: 3️⃣ 抓取商品信息")
   ## clarks_fetch_info()

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    ## import_txt_to_db_supplier("clarks_jingya")  # ✅ 新逻辑

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
   ##  insert_jingyaid_to_db("clarks_jingya")

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
   ##  insert_missing_products_with_zero_stock("clarks_jingya")

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    ##generate_publication_excels("clarks_jingya")

    print("导出发布商品的价格")
    export_channel_price_excel_from_txt("clarks_jingya",code_file_path)

    print("\\n🟡 Step: 6️⃣ 导出渠道价格 Excel（含零售价与商家编码），可以用于淘宝店铺去更新商品价格")
    # export_channel_price_excel("clarks_jingya")  # 导出价格明细（已发布）

    print("\\n🟡 Step: 6️⃣ 导出男鞋商品列表，女鞋商品列表，用于更新尺码库存数据库版")
    #export_gender_split_excel("clarks_jingya")

if __name__ == "__main__":
    main()