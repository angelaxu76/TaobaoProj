"""
此脚本用于渠道产品管理，按性别导出商品 Excel（不影响主产品发布流程）
"""

from common_taobao.jingya.export_gender_split_excel import export_gender_split_excel

def run_channel_product_split():
    print("\n📦 渠道产品管理：导出男女款商品编码与渠道ID")
    export_gender_split_excel("camper")

if __name__ == "__main__":
    run_channel_product_split()