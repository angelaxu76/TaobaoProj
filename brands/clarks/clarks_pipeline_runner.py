
from brands.clarks.clarks_scraper import ClarksScraper
from common_taobao.db_import import import_txt_to_db
from common_taobao.export_discount_price import export_discount_excel
from brands.clarks.export_skuid_stock import export_stock_excel
from common_taobao.prepare_publication import prepare_products
from common_taobao.generate_reports import generate_publish_report
from config import CLARKS, PGSQL_CONFIG
import psycopg2
import shutil
import datetime

from common_taobao.backup_and_clear_txt import backup_and_clear_txt

def backup_and_clear_publication():
    pub_dir = CLARKS["BASE"] / "publication"
    backup_base = CLARKS["BASE"] / "backup"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / f"publication_{timestamp}"

    # 备份整个 publication
    if pub_dir.exists():
        shutil.copytree(pub_dir, backup_dir)
        print(f"📦 已备份 publication → {backup_dir}")
    # 清空 TXT（使用通用模块）
    backup_and_clear_txt(CLARKS["TXT_DIR"], CLARKS["BASE"] / "backup")

def main():
    backup_and_clear_publication()

    scraper = ClarksScraper()
    link_file = CLARKS["BASE"] / "publication" / "product_links.txt"
    txt_dir = CLARKS["TXT_DIR"]
    image_dir = CLARKS["IMAGE_DIR"]
    output_dir = CLARKS["OUTPUT_DIR"]
    store_id = "2219163936872"

    # Step 1: 抓取信息
    print("\n🟡 Step 1：抓取商品信息")
    with open(link_file, "r", encoding="utf-8") as f:
        for url in [line.strip() for line in f if line.strip()]:
            try:
                product = scraper.fetch_product_info(url)
                code = product["Product Code"]
                txt_file = txt_dir / f"{code}.txt"
                with open(txt_file, "w", encoding="utf-8") as f_txt:
                    for key, value in product.items():
                        f_txt.write(f"{key}: {value}\n")
                print(f"✅ 信息已保存: {code}")
            except Exception as e:
                print(f"❌ 信息抓取失败: {url} - {e}")

    # Step 2: 下载图片
    print("\n🟡 Step 2：下载商品图片")
    with open(link_file, "r", encoding="utf-8") as f:
        for url in [line.strip() for line in f if line.strip()]:
            try:
                scraper.fetch_product_images(url, image_dir)
                print(f"✅ 图片下载完成: {url}")
            except Exception as e:
                print(f"❌ 图片下载失败: {url} - {e}")

    # Step 3: 导入数据库
    print("\n🟡 Step 3：导入 TXT 数据到数据库")
    conn = psycopg2.connect(**PGSQL_CONFIG)
    import_txt_to_db(txt_dir=txt_dir, brand="clarks", conn=conn)

    # Step 4: 导出打折价 Excel
    print("\n🟡 Step 4：导出打折价格 Excel")
    export_discount_excel(txt_dir, "clarks", output_dir / "打折价格.xlsx")

    # Step 5: 导出库存 Excel
    print("\n🟡 Step 5：导出库存 Excel")
    export_stock_excel(txt_dir, "clarks", store_id, output_dir / "库存信息.xlsx")

    # Step 6: 准备发布商品
    print("\n🟡 Step 6：准备发布商品")
    prepare_products(txt_dir, image_dir, output_dir, "clarks")

    # Step 7: 发布报告
    print("\n🟡 Step 7：生成发布状态报告")
    published_codes = set()
    generate_publish_report(txt_dir, "clarks", published_codes, output_dir / "发布状态报告.xlsx")

    print("\n✅ 全部流程执行完毕")

if __name__ == "__main__":
    main()
