from common_taobao.jingya.extract_unpublished_ids_binding_taobaostore import  extract_unpublished_ids
from common_taobao.jingya.export_channel_price_excel import export_channel_price_excel_from_txt,export_channel_price_excel
from config import CAMPER

def main():
    #parse_and_update_excel("camper")

    #找出没有绑定淘宝店铺的商品ID
    #extract_unpublished_ids(CAMPER)

    # === 仅仅输出txt_path文件中包含 channel_product_id的列表
    #export_channel_price_excel_from_txt("camper",r"D:\TB\Products\camper\repulibcation\channel_product_id_unprocessed.txt")
    export_channel_price_excel("camper")
if __name__ == "__main__":
    main()