"""
此脚本用于渠道产品管理，按性别导出商品 Excel（不影响主产品发布流程）
"""

from channels.jingya.export.export_gender_split_excel import export_recently_published_excel
from channels.jingya.ingest.import_channel_info import insert_JingyaId_toDB
from channels.jingya.maintenance.copy_recent_publication_images import copy_product_images_for_recent_publication
from channels.taobao.legacy.export_channel_price_excel import export_channel_price_excel,export_all_sku_price_excel
from channels.jingya.export.export_gender_split_excel import export_gender_split_excel

def run_channel_product_split():
    print("\n📦 渠道产品管理：导出男女款商品编码与渠道ID")
    export_recently_published_excel("camper")

if __name__ == "__main__":
    # 将GEI excel中的产品的货品ID等鲸牙这边的数据导入数据库
    parse_and_update_excel("camper")

    run_channel_product_split()

    copy_product_images_for_recent_publication("camper")

    export_channel_price_excel("camper")

    export_all_sku_price_excel("camper")

    export_gender_split_excel("camper")


