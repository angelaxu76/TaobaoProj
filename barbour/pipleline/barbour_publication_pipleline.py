from pathlib import Path
from barbour.generate_barbour_publication_excel import generate_publication_excel
from tools.image.image_composer_background import image_composer
from config import BARBOUR
from barbour.image_move_for_publication_folder import move_image_for_publication
from barbour.generate_barbour_prices_from_avg import generate_price_for_jingya_publication
from barbour.insert_jingyaid_to_db_barbour import insert_jingyaid_to_db,insert_missing_products_with_zero_stock


def pipeline_barbour():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")


    # 步骤 1：将产品的编码放到D:\TB\Products\barbour\repulibcation\codes.txt
    # 步骤 2：生成发布产品的excel
    print("\n🌐 步骤 1：抓取商品链接")
    #generate_publication_excel()

    print("\n步骤 2：生成透明图+背景图")
    fg_dir=Path(r"D:\TB\Products\barbour\images\透明图")
    bg_dir = Path(r"D:\TB\Products\barbour\images\backgrounds")
    out_dir= Path(r"D:\TB\Products\barbour\images\output")
    #image_composer(fg_dir,bg_dir,out_dir,6)

    print("\n步骤 3：准备发布商品的图片并列出missing的图片")
    codes_file   = BARBOUR["OUTPUT_DIR"] / "codes.txt"
    out_dir_src  = Path(r"D:\TB\Products\barbour\images\output")
    dest_img_dir = BARBOUR["OUTPUT_DIR"] / "images"
    missing_file = BARBOUR["OUTPUT_DIR"] / "missing_image.txt"
    #move_image_for_publication(codes_file, out_dir_src, dest_img_dir, missing_file)

    print("\n步骤 4：生成价格表")
    DEFAULT_INFILE = BARBOUR["OUTPUT_DIR"] / "channel_products.xlsx"
    DEFAULT_OUTFILE = BARBOUR["OUTPUT_DIR"] / "barbour_price_quote.xlsx"
    #generate_price_for_jingya_publication(DEFAULT_INFILE,DEFAULT_OUTFILE)

    print("\n步骤 5：将鲸芽商品编码和尺码和相关ID插入数据库占位,库存初始化为0")
    insert_missing_products_with_zero_stock("barbour")
    insert_jingyaid_to_db("barbour")



if __name__ == "__main__":
    pipeline_barbour()