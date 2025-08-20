from barbour.supplier.allweathers_fetch_info import fetch_allweathers_products
from barbour.supplier.allweathers_get_links import allweathers_get_links
from barbour.common.import_supplier_to_db_offers import import_txt_for_supplier

def pipeline_houseoffraser():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")

    # 步骤 1：抓取商品链接
    print("\n🌐 步骤 1：抓取商品链接")
    allweathers_get_links()

    # 步骤 2：抓取商品详情并生成 TXT
    print("\n📦 步骤 2：抓取商品详情并生成 TXT")
    fetch_allweathers_products(7)

    # Step 3: TODO 将txt中数据导入barbour product中
    # batch_import_txt_to_barbour_product("allweathers")

    # Step 4: TODO 将txt中数据导入数据库offers
    import_txt_for_supplier("allweathers")

    print("\n✅ allweathers 全部流程完成！")

if __name__ == "__main__":
    pipeline_houseoffraser()