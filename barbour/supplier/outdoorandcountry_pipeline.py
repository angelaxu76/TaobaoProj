# pipeline_outdoorandcountry.py
# ✅ 用于抓取 Outdoor and Country 网站的 Barbour 商品链接并后续处理

import subprocess
from pathlib import Path
from config import BARBOUR
from barbour.supplier.outdoorandcountry_get_links import outdoorandcountry_fetch_and_save_links
from barbour.supplier.outdoorandcountry_fetch_info import fetch_outdoor_product_offers_concurrent
from barbour.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.supplier_import_to_barbour_products import batch_import_txt_by_supplier
def run_step(desc, cmd):
    print(f"\n🟢 {desc}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ 步骤失败: {desc}")
        exit(1)

def main():
    print("🚀 启动 Barbour - Outdoor and Country 抓取流程")
    #outdoorandcountry_fetch_and_save_links()

    # Step 2: TODO 后续可集成 fetch_product_info.py（解析库存、价格）
    #fetch_outdoor_product_offers_concurrent(max_workers=7)

    # Step 3: TODO 将txt中数据导入barbour product中
    #batch_import_txt_by_supplier("outdoorandcountry")

    # Step 4: TODO 将txt中数据导入数据库offers
    import_txt_for_supplier("outdoorandcountry")

    print("\n✅ 全部流程完成")

if __name__ == "__main__":
    main()