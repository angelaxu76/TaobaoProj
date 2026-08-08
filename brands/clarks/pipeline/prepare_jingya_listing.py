import os
import subprocess
from config import CLARKS
from channels.jingya.ingest.import_channel_info import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs
from brands.clarks.collect_product_links import generate_product_links
from brands.clarks.collect_ebay_product_names import generate_ebay_product_names
from brands.clarks.fetch_product_info import clarks_fetch_info
from brands.clarks.fetch_product_info_v2 import clarks_outlet_fetch_info_v2, write_regular_links_file
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.export.generate_publication_excel_shoes import generate_publication_excels
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand
from channels.jingya.maintenance.generate_empty_product_links_for_brand import generate_empty_product_links_for_brand

# def run_script(filename: str):
#     path = os.path.join(os.path.dirname(__file__), filename)
#     print(f"⚙️ 执行脚本: {filename}")
#     subprocess.run(["python", path], check=True)

def main():
    code_file_path = r"D:\TB\Products\clarks\repulibcation\publication_codes.txt"
    
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录")
    backup_and_clear_brand_dirs(CLARKS)  # ✅ 使用共享方法

    print("\n🟡 Step: 2️⃣ 抓取商品链接") 
    generate_product_links("clarks")

    print("\n🟡 Step: 3️⃣ 抓取 eBay 商品名称列表")
    generate_ebay_product_names("clarks")

    print("\n🟡 Step: 3️⃣ 抓取商品信息（正规官网 www.clarks.com，全量不过滤）")
    regular_links_file = write_regular_links_file()
    clarks_fetch_info(str(regular_links_file))

    print("\n🟡 Step: 3️⃣ 抓取商品信息（Outlet，按 eBay 商品名称过滤）")
    outlet_matched_total, outlet_skipped_total = clarks_outlet_fetch_info_v2()

    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\clarks\publication\missing_product_links.txt"
    generate_missing_links_for_brand("clarks", missing_product_link)
    if os.path.exists(missing_product_link):
        missing_regular_file = write_regular_links_file(
            missing_product_link,
            CLARKS["BASE"] / "publication" / "missing_product_links_regular.txt",
        )
        clarks_fetch_info(str(missing_regular_file))
        matched, skipped = clarks_outlet_fetch_info_v2(missing_product_link)
        outlet_matched_total += matched
        outlet_skipped_total += skipped

    print("\n🟡 Step: 3️⃣ 找出TXT中价格/库存全空的商品（网络原因导致抓取失败），重新抓一遍")
    empty_product_link = generate_empty_product_links_for_brand("clarks")
    if empty_product_link.exists() and empty_product_link.stat().st_size > 0:
        empty_regular_file = write_regular_links_file(
            str(empty_product_link),
            CLARKS["BASE"] / "publication" / "empty_product_links_regular.txt",
        )
        clarks_fetch_info(str(empty_regular_file))
        matched, skipped = clarks_outlet_fetch_info_v2(str(empty_product_link))
        outlet_matched_total += matched
        outlet_skipped_total += skipped
    else:
        print("  - 无空数据商品，跳过")

    print(
        f"\n🟢 Outlet 商品汇总：eBay 匹配写入 TXT {outlet_matched_total} 条，"
        f"eBay 未找到跳过 {outlet_skipped_total} 条"
    )

    print("\n🟡 Step: 4️⃣ 导入 TXT → 数据库，如果库存低于2的直接设置成0")
    import_txt_to_db_supplier("clarks")

    print("\n🟡 Step: 5️⃣ 绑定渠道 SKU 信息（淘经销 Excel）将鲸芽那边的货品ID等输入到数据库")
    insert_jingyaid_to_db("clarks", debug=True)

    print("\n🟡 Step: 5️⃣ 将最新TXT中没有的产品，说明刚商品已经下架，但鲸芽这边没办法删除，全部补库存为0")
    insert_missing_products_with_zero_stock("clarks")


    print("\n🟡 Step: 6️⃣ 获取excel文件用来更新淘宝店铺价格")
    generate_price_excels_bulk(
        brand="clarks",
        input_dir=r"\\vmware-host\Shared Folders\shared\clarks\store_prices",
        output_dir=r"\\vmware-host\Shared Folders\VMShared\clarks\store_prices",
        suffix="_价格",                # 输出文件后缀，可改成 _for_import 等
        drop_rows_without_price=False,
        blacklist_excel_file=r"\\vmware-host\Shared Folders\shared\clarks\exclude.xlsx" # 不丢行，查不到的价格留空
    )


    print("\\n🟡 Step: 6️⃣ 导出库存用于更新")
    stock_dest_excel_folder = r"\\vmware-host\Shared Folders\VMShared\input"
    export_stock_excel("clarks",stock_dest_excel_folder)

    price_dest_excel = r"\\vmware-host\Shared Folders\VMShared\clarks\publication_prices"
    export_jiangya_channel_prices("clarks",price_dest_excel,chunk_size=200)

    print("\\n🟡 Step: 6️⃣生成发布产品的excel")
    generate_publication_excels("clarks")

if __name__ == "__main__":
    main()