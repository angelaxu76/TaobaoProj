from pathlib import Path
from config import BARBOUR
from barbour.jingya.insert_jingyaid_to_db_barbour import insert_jingyaid_to_db,insert_missing_products_with_zero_stock
from barbour.common.export_barbour_discounts import export_barbour_discounts_excel
from barbour.common.generate_barbour_publication_excel import generate_publication_excel
from barbour.common.generate_sql_for_pulication import generate_select_sql_from_excel
from barbour.common.generate_barbour_prices_from_avg import generate_price_for_jingya_publication


def pipeline_barbour():
    print("\n🚀 启动 Barbour - House of Fraser 全流程抓取")

    # 步骤 1：导出打折的商品可以发布的商品列表到excel
    # excel_path = export_barbour_discounts_excel(0, 3, "LCA")
    # print(excel_path)

    # 步骤 1：将产品的编码放到D:\TB\Products\barbour\repulibcation\codes.txt
    # 步骤 2：生成发布产品的excel
    # print("\n🌐 步骤 1：抓取商品链接")
    generate_publication_excel()

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
    # generate_price_for_jingya_publication(DEFAULT_OUTFILE)

    print("\n步骤 5：将鲸芽商品编码和尺码和相关ID插入数据库占位,库存初始化为0")
    #insert_missing_products_with_zero_stock("barbour")
    #insert_jingyaid_to_db("barbour")

    print("\n步骤 6：生成更新数据库的SQL String给UIPath使用，去更新库存")
    # result = generate_select_sql_from_excel(r"D:\TB\Products\barbour\document\publication\barbour_publication_20250907_222647.xlsx")
    # print(result["preview"])


if __name__ == "__main__":
    pipeline_barbour()