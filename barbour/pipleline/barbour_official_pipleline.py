from barbour.supplier.barbour_get_links import barbour_get_links
from barbour.supplier.barbour_fetch_info import barbour_fetch_info
from barbour.common.import_supplier_to_db_offers import import_txt_for_supplier

def pipeline_barbour():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")

    # 步骤 1：抓取商品链接
    print("\n🌐 步骤 1：抓取商品链接")
    barbour_get_links()

    # 步骤 2：抓取商品详情并生成 TXT
    print("\n📦 步骤 2：抓取商品详情并生成 TXT")
    barbour_fetch_info()

    # Step 3: TODO 将txt中数据导入barbour product中
    #batch_import_txt_to_barbour_product("barbour")

    # Step 4: TODO 将txt中数据导入数据库offers
    import_txt_for_supplier("barbour")

    print("\n✅ barbour 全部流程完成！")

if __name__ == "__main__":
    pipeline_barbour()