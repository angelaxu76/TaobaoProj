from barbour.supplier.houseoffraser_get_links import houseoffraser_get_links
from barbour.supplier.houseoffraser_fetch_info import fetch_all
from barbour.import_supplier_to_db_offers import import_txt_for_supplier

def pipeline_houseoffraser():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")

    # 步骤 1：抓取商品链接
    print("\n🌐 步骤 1：抓取商品链接")
    #houseoffraser_get_links()

    # 步骤 2：抓取商品详情并生成 TXT
    print("\n📦 步骤 2：抓取商品详情并生成 TXT")
    fetch_all()

    # 步骤 3：将 TXT 数据导入 offers 表
    print("\n🗃️ 步骤 3：导入数据库 offers 表")
    #import_txt_for_supplier("houseoffraser")

    print("\n✅ House of Fraser 全部流程完成！")
    import_txt_for_supplier("houseoffraser")

if __name__ == "__main__":
    pipeline_houseoffraser()