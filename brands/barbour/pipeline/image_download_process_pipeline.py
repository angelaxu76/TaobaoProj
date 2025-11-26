from pathlib import Path
from helper.image.image_antifingerprint import batch_process_images
from helper.image.expand_square_add_code import process_images
from helper.html.html_to_png_batch import process_html_folder
from helper.image.trim_sides_batch import trim_sides_batch
from helper.image.split_image_by_size import split_image_by_size
from helper.image.add_text_watermark import pipeline_text_watermark
from helper.image.cut_square_white_watermark import batch_process
from helper.image.avif_to_jpg import avif_to_jpg
from brands.barbour.supplier.barbour_download_images_only import download_barbour_images,download_barbour_images_multi
from common_taobao.image.group_images_by_code import group_and_rename_images
from config import BARBOUR

def main():

    print("从barbour官网下载图片")
    download_barbour_images_multi(max_workers=6)

    print("给Barbour图片做防指纹处理")
    batch_process_images(IMAGE_IN=BARBOUR['IMAGE_DOWNLOAD'], 
                         IMAGE_OUT=BARBOUR['IMAGE_DOWNLOAD'])

    print("将Barbour图片按编码分组并重命名")
    group_and_rename_images(BARBOUR['IMAGE_DOWNLOAD'], code_len=11, overwrite=True)

    # print("将JPG转AVIF")
    # avif_to_jpg(input_dir=r"C:\Users\martin\Downloads", output_dir=r"C:\Users\martin\Downloads")



    print("将JPG按长度切分")
    # split_image_by_size(CUTTER_FOLDER,SPLIT_FOLDER,1900)
    # process_images(
    #     input_dir=r"C:\Users\martin\Downloads",
    #     output_dir=r"D:\TB\Products\barbour\images",
    #     product_code="LQU0471OL91",
    #     defend=True, 
    # )

    # batch_process(r"D:\TB\Products\barbour\3", r"D:\TB\Products\barbour\3_processed111", max_workers=3)
 
    # process_images(
    #     input_dir=r"D:\TB\Products\barbour\3",
    #     output_dir=r"D:\TB\Products\barbour\3_processed",
    #     product_code="barbour",
    #     defend=True,                 # 是否做扰动
    #     watermark=True,              # 是否加水印
    #     wm_text="英国哈梅尔百货",           # 斜纹文字水印
    #     wm_logo_text="英国哈梅尔百货"       # 右下角小文字水印
    # )

    # pipeline_text_watermark(input_dir=r"C:\Users\martin\Desktop\main",
    #                     output_dir=r"C:\Users\martin\Desktop\mainwatered")


    # HTML_FOLDER = Path(r"D:/TB/HTMLToImage/input")
    # OUTPUT_FOLDER = Path(r"D:/TB/HTMLToImage/output")
    # CUTTER_FOLDER = Path(r"D:/TB/HTMLToImage/cutter")
    # SPLIT_FOLDER = Path(r"D:/TB/HTMLToImage/split")

    # print("将html转JPG")
    # process_html_folder(HTML_FOLDER,OUTPUT_FOLDER)

    # print("将JPG切白边")
    # result = trim_sides_batch(OUTPUT_FOLDER,CUTTER_FOLDER)

    print("\n步骤 2：生成透明图+背景图")
    # fg_dir=Path(r"D:\TB\Products\barbour\images\透明图")
    # bg_dir = Path(r"D:\TB\Products\barbour\images\backgrounds")
    # out_dir= Path(r"D:\TB\Products\barbour\images\output")
    #image_composer(fg_dir,bg_dir,out_dir,6)

    print("\n步骤 3：准备发布商品的图片并列出missing的图片")
    # codes_file   = BARBOUR["OUTPUT_DIR"] / "codes.txt"
    # out_dir_src  = Path(r"D:\TB\Products\barbour\images\output")
    # dest_img_dir = BARBOUR["OUTPUT_DIR"] / "images"
    # missing_file = BARBOUR["OUTPUT_DIR"] / "missing_image.txt"
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
        main()