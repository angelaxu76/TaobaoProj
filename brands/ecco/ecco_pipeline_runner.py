import os
import shutil
import subprocess
from datetime import datetime
from config import ECCO

# ✅ 店铺列表
stores = ECCO["STORES"]
brand = "ecco"

def backup_and_clear_publication():
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    for store in stores:
        pub_dir = ECCO["OUTPUT_DIR"] / store
        backup_dir = ECCO["BACKUP_DIR"] / now / store
        if pub_dir.exists():
            shutil.copytree(pub_dir, backup_dir)
            print(f"📦 [{store}] 已备份: {pub_dir} → {backup_dir}")
            for item in pub_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            print(f"🧹 [{store}] 已清空发布目录")

def run_script(script, args=None):
    path = os.path.join(os.path.dirname(__file__), script)
    cmd = ["python", path]
    if args:
        cmd += args
    subprocess.run(cmd, check=True)

def main():
    print("🟡 Step: 1️⃣ 备份并清空所有店铺发布目录")
    backup_and_clear_publication()

    print("\n🟡 Step: 2️⃣ 抓取商品链接")
    run_script("unified_link_collector.py")

    print("\n🟡 Step: 3️⃣ 下载商品信息与图片")
    run_script("fetch_product_info.py")

    print("\n🟡 Step: 4️⃣ 将 TXT 写入数据库")
    run_script("import_ecco_txt_to_db.py")

    print("\n🟡 Step: 5️⃣ 导出定价 Excel")
    run_script("export_discount_price_excel.py")

    print("\n🟡 Step: 6️⃣ 导出库存 Excel")
    run_script("export_skuid_stock.py")

    print("\n🟡 Step: 7️⃣ 为每个店铺生成发布用 Excel + 拷贝图片")
    for store in stores:
        run_script("generate_product_excels.py", ["--brand", brand, "--store", store])

if __name__ == "__main__":
    main()