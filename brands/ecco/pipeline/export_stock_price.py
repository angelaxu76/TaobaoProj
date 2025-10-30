from xml.dom.minidom import Document
from config import ECCO
from common_taobao.maintenance.backup_and_clear import backup_and_clear_brand_dirs

# ====== 抓取阶段（沿用 ECCO 原逻辑）======
from brands.ecco.collect_product_links import ecco_get_links
from brands.ecco.fetch_product_info import ecco_fetch_info

# ====== 数据入库 & 绑定阶段（照 Camper 逻辑）======
from channels.jingya.ingest.import_txt_to_db import import_txt_to_db_supplier
from channels.jingya.ingest.import_channel_info import (
    insert_jingyaid_to_db,
    insert_missing_products_with_zero_stock,
)

# ====== 风险控管/库存下架（可选，同 Camper）======
from channels.jingya.maintenance.disable_low_stock_products import disable_low_stock_products
# from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel
from common_taobao.publication.export_low_stock_products import export_low_stock_for_brand

# ====== 导出给鲸芽的库存&价格 ======
from channels.jingya.export.export_stock_to_excel import export_stock_excel
from channels.jingya.export.export_channel_price_excel_jingya import export_jiangya_channel_prices

# ====== 新品上架模板（鲸芽）======
from channels.jingya.export.generate_publication_excel import generate_publication_excels

# ====== 给淘宝店铺同步价格（沿用 Camper 通用逻辑，可选保留）======
from common_taobao.publication.generate_taobao_store_price_for_import_excel import generate_price_excels_bulk


def main():
    print("\n🟡 Step: 1️⃣ 清空 TXT + 发布目录 (ECCO)")    
    # print("\n🟡 Step: 6️⃣ 生成鲸芽【库存更新】Excel")
    # stock_dest_excel_folder = r"D:\TB\Products\ecco\repulibcation\stock"
    # export_stock_excel("ecco", stock_dest_excel_folder)

    # print("\n🟡 Step: 6️⃣ 生成鲸芽【价格更新】Excel")
    # price_dest_excel_folder = r"D:\TB\Products\ecco\repulibcation\publication_prices"
    # exclude_xlsx_path = r"D:\TB\Products\ECCO\document\exclude_list.xlsx"
    # export_jiangya_channel_prices(brand="ecco", output_dir=price_dest_excel_folder, exclude_excel_file=exclude_xlsx_path)

    # print("\n🟡 Step: 7️⃣ 为新品生成【鲸芽上新模板】Excel")
    # generate_publication_excels("ecco")

    # print("\n🟡 Step: 8️⃣ 输出低库存商品列表，准备在鲸芽下架")
    # export_low_stock_for_brand("ecco", threshold=5)

    # print("\n🟡 Step: 9️⃣ 生成淘宝店铺价格导入文件（可选，沿用 Camper 的店铺价逻辑）")
    # generate_price_excels_bulk(
    #     brand="ecco",
    #     input_dir=r"D:\TB\Products\ecco\repulibcation\store_prices\input",
    #     output_dir=r"D:\TB\Products\ecco\repulibcation\store_prices\output",
    #     suffix="_价格",
    #     drop_rows_without_price=False
    # )


    # print("\n🟡 Step: 5️⃣ 导出男/女商品列表（可用于手工核对）")
    #     export_gender_split_excel("ecco")
    #     print("\n✅ ECCO 鲸芽 pipeline 完成")


if __name__ == "__main__":
    main()
