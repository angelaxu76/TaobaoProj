from config import ECCO
from common.maintenance.backup_and_clear import backup_and_clear_brand_dirs

# ====== 抓取阶段（沿用 ECCO 原逻辑）======
from brands.ecco.collect_product_links_v3 import ecco_get_links
from brands.ecco.fetch_product_info import ecco_fetch_info

# ====== 数据入库 & 绑定阶段（照 Camper 逻辑）======
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.ingest.import_channel_info import (
    insert_jingyaid_to_db,
    insert_missing_products_with_zero_stock,
)

# ====== 风险控管/库存下架（可选，同 Camper）======
from channels.jingya.maintenance.disable_low_stock_products import disable_low_stock_products
# from common.jingya.export_gender_split_excel import export_gender_split_excel
from channels.jingya.maintenance.export_low_stock_products import export_low_stock_for_brand

# ====== 导出给鲸芽的库存&价格 ======
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices

# ====== 新品上架模板（鲸芽）======
from channels.jingya.export.generate_publication_excel_shoes import generate_publication_excels

# ====== 给淘宝店铺同步价格（沿用 Camper 通用逻辑，可选保留）======
from channels.jingya.pricing.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk
from channels.jingya.maintenance.generate_missing_links_for_brand import generate_missing_links_for_brand

def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录 (ECCO)")
    backup_and_clear_brand_dirs(ECCO)

    print("\n🟡 Step: 2️⃣ 抓取 ECCO 商品链接")
    ecco_get_links()

    print("\n🟡 Step: 3️⃣ 抓取 ECCO 商品信息 & 生成 TXT")
    ecco_fetch_info()


    print("\n🟡 Step: 3️⃣ 将鲸牙存在但TXT中不存在的商品抓一遍")
    missing_product_link = r"D:\TB\Products\ecco\publication\missing_product_links.txt";
    generate_missing_links_for_brand("ecco",missing_product_link )
    ecco_fetch_info(missing_product_link )

    print("\n🟡 Step: 4️⃣ TXT 导入数据库（鲸芽专用结构）")
    import_txt_to_db_supplier("ecco")
    print("─" * 60)

    print("\n🟡 Step: 5️⃣ 导入鲸芽渠道Excel，写入渠道商品ID/SKUID 绑定关系")
    insert_jingyaid_to_db("ecco")
    print("─" * 60)

    print("\n🟡 Step: 5️⃣ 处理已下架商品：补库存=0，防止违规超卖")
    insert_missing_products_with_zero_stock("ecco")
    print("─" * 60)

    # print("\n🟡 Step: 5️⃣ 根据尺码数量，自动下架稀缺尺码的商品，避免差评/售后")
    # disable_low_stock_products("ecco", min_sizes=1)
    # print("─" * 60)

  

    print("\n🟡 Step: 6️⃣ 生成鲸芽【库存更新】Excel")
    stock_dest_excel_folder = r"\\vmware-host\Shared Folders\VMShared\input"
    export_stock_excel("ecco", stock_dest_excel_folder)

    print("\n🟡 Step: 6️⃣ 生成鲸芽【价格更新】Excel")
    price_dest_excel_folder = r"D:\TB\Products\ecco\repulibcation\publication_prices"
    export_jiangya_channel_prices("ecco", price_dest_excel_folder)

    print("\n🟡 Step: 7️⃣ 为新品生成【鲸芽上新模板】Excel")
    generate_publication_excels("ecco")

    print("\n🟡 Step: 9️⃣ 生成淘宝店铺价格导入文件（可选，沿用 Camper 的店铺价逻辑）")
    generate_price_excels_bulk(
        brand="ecco",
        input_dir=r"D:\TB\Products\ECCO\document\store_prices",
        output_dir=r"D:\TB\Products\ecco\repulibcation\store_prices",
        suffix="_价格",
        drop_rows_without_price=False,
        blacklist_excel_file=r"\\vmware-host\Shared Folders\shared\ecco\exclude.xlsx" # 不丢行，查不到的价格留空
    )



    print("\n✅ ECCO 鲸芽 pipeline 完成")


if __name__ == "__main__":
    main()
