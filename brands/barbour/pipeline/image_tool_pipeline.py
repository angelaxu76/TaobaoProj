from pathlib import Path
from helper.image.expand_square_add_code import process_images
from helper.html.html_to_png_batch import process_html_folder
from helper.image.trim_sides_batch import trim_sides_batch
from helper.image.split_image_by_size import split_image_by_size
from helper.image.add_text_watermark import pipeline_text_watermark
from helper.image.cut_square_white_watermark import batch_process
from helper.image.avif_to_jpg import avif_to_jpg
from brands.barbour.supplier.barbour_download_images_only import download_barbour_images

def main():
    # HTML_FOLDER = Path(r"D:/TB/HTMLToImage/input")
    # OUTPUT_FOLDER = Path(r"D:/TB/HTMLToImage/output")
    # CUTTER_FOLDER = Path(r"D:/TB/HTMLToImage/cutter")
    # SPLIT_FOLDER = Path(r"D:/TB/HTMLToImage/split")

    # print("将html转JPG")
    # process_html_folder(HTML_FOLDER,OUTPUT_FOLDER)

    # print("将JPG切白边")
    # result = trim_sides_batch(OUTPUT_FOLDER,CUTTER_FOLDER)

    # print("从barbour官网下载图片")
    download_barbour_images()

    print("将JPG转AVIF")
    # avif_to_jpg(input_dir=r"C:\Users\martin\Downloads", output_dir=r"C:\Users\martin\Downloads")



    # print("将JPG按长度切分")
    # split_image_by_size(CUTTER_FOLDER,SPLIT_FOLDER,1900)
    # process_images(
    #     input_dir=r"C:\Users\martin\Downloads",
    #     output_dir=r"D:\TB\Products\barbour\images",
    #     product_code="LQU1866BK91",
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


if __name__ == "__main__":
        main()