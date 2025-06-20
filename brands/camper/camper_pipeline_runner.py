import subprocess
from datetime import datetime
from pathlib import Path
import shutil
import sys

brand = "camper"
store_list = ["TODO_店铺名称1", "TODO_店铺名称2"]
BASE_DIR = Path(f"D:/TB/Products/{camper}")
BACKUP_DIR = BASE_DIR / "backup"
REPU_DIR = BASE_DIR / "repulibcation"

def step(msg): print(f"\n🟡 Step: {{msg}}")

def run_script(path):
    subprocess.run([sys.executable, path], check=True)

def backup_and_clear_publication(store):
    pub_dir = REPU_DIR / store
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / timestamp / store
    if pub_dir.exists():
        shutil.copytree(pub_dir, backup_path, dirs_exist_ok=True)
        print(f"📦 [{{store}}] 已备份: {{pub_dir}} → {{backup_path}}")
        for item in pub_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        print(f"🧹 [{{store}}] 已清空发布目录")

def main():
    step("1️⃣ 备份并清空所有店铺发布目录")
    for store in store_list:
        backup_and_clear_publication(store)

    step("2️⃣ 抓取商品链接")
    run_script("unified_link_collector.py")

    step("3️⃣ 下载商品 TXT 和图片")
    run_script("fetch_product_info.py")

    step("4️⃣ 导入 TXT 信息到数据库")
    run_script("import_camper_txt_to_db.py")

    step("5️⃣ 导出定价 Excel")
    run_script("generate_discount_price_excel.py")

    step("6️⃣ 导出库存 Excel")
    run_script("export_skuid_stock.py")

    step("7️⃣ 为每个店铺生成发布用 Excel + 拷贝图片")
    for store in store_list:
        subprocess.run([sys.executable, "generate_product_excels.py", "--brand", brand, "--store", store], check=True)

    print("\n✅ 所有店铺流程执行完毕")

if __name__ == "__main__":
    main()
