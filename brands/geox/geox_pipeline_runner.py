import os
import shutil
import subprocess
from datetime import datetime
from config import GEOX
from pathlib import Path

# 路径配置
BASE_DIR = GEOX["BASE"]
PUBLICATION_DIR = BASE_DIR / "publication"
REPUB_DIR = GEOX["OUTPUT_DIR"]
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

def run_script(filename: str, args=None):
    args = args or []
    path = os.path.join(os.path.dirname(__file__), filename)
    print(f"⚙️ 执行脚本: {filename}")
    subprocess.run(["python", path] + args, check=True)

def main():
    print("\n🟡 Step: 1️⃣ 备份并清空目录: repulibcation")
    if REPUB_DIR.exists():
        store_list = [folder.name for folder in REPUB_DIR.iterdir() if folder.is_dir()]
        for store in store_list:
            backup_and_clear_dir(REPUB_DIR / store, f"repulibcation/{store}")
    else:
        print(f"⚠️ 发布目录不存在: {REPUB_DIR}，跳过店铺处理步骤")
        store_list = []

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
   # run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣a 下载商品信息（不含图片）")
    run_script("fetch_product_info.py")

    print("\n🟡 Step: 3️⃣b 下载商品图片")
    run_script("download_images_only.py")

    print("\n🟡 Step: 4️⃣ 导入 TXT + SKU ID")
    run_script("import_geox_txt_to_db.py")

    print("\n🟡 Step: 5️⃣ 导出商品价格")
    run_script("generate_discount_price_excel.py")

    print("\n🟡 Step: 6️⃣ 导出商品库存")
    run_script("export_skuid_stock.py")

    print("\n🟡 Step: 7️⃣ 为每个店铺生成发布用 Excel + 拷贝图片")
    for store in store_list:
        run_script("generate_product_excels.py", ["--brand", "geox", "--store", store])

    print("\n✅ GEOX pipeline 执行完毕")

if __name__ == "__main__":
    main()