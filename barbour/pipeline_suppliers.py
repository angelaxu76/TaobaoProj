# pipeline_outdoorandcountry.py
# ✅ 用于抓取 Outdoor and Country 网站的 Barbour 商品链接并后续处理

import subprocess
from pathlib import Path
from config import BARBOUR
from barbour.supplier.get_outdoorandcountry_links import outdoorandcountry_fetch_and_save_links
from barbour.supplier.outdoorcountry_fetch_info import fetch_outdoor_product_offers
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
    fetch_outdoor_product_offers()


    print("\n✅ 全部流程完成")

if __name__ == "__main__":
    main()