# pipeline_outdoorandcountry.py
# ✅ 用于抓取 Outdoor and Country 网站的 Barbour 商品链接并后续处理

import subprocess
from pathlib import Path
from config import BARBOUR
from barbour.supplier.philipmorrisdirect_get_links import philipmorris_get_links
from barbour.supplier.philipmorrisdirect_fetch_info import fetch_all
from barbour.import_supplier_to_db_offers import import_txt_for_supplier
from barbour.supplier_import_to_barbour_products import batch_import_txt_to_barbour_product
def run_step(desc, cmd):
    print(f"\n🟢 {desc}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ 步骤失败: {desc}")
        exit(1)

def main():
    print("🚀 启动 Barbour - Outdoor and Country 抓取流程")
    #  philipmorris_get_links()

    # Step 2: TODO 后续可集成 fetch_product_info.py（解析库存、价格）
    fetch_all()

    # Step 3: TODO 将txt中数据导入barbour product中
    #batch_import_txt_to_barbour_product("outdoorandcountry")

    # Step 4: TODO 将txt中数据导入数据库offers
    # import_txt_for_supplier("outdoorandcountry")

    print("\n✅ 全部流程完成")

if __name__ == "__main__":
    main()