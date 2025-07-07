from brands.ecco.download_images_only import  download_images_by_code_file
from common_taobao.tools.image_defender_leftright import batch_process_images
from common_taobao.tools.crop_gray_to_square import run_crop_and_expand
from brands.ecco.image.ImageMaxCutter import batch_convert_webp_to_jpg,process_images_in_folder

from config import ECCO
from pathlib import Path


def main():
    print("下载指定商品编码的的图片")
    #download_images_by_code_file(r"D:\TB\Products\ecco\repulibcation\五小剑\missing_images.txt")

    print("最大化裁剪，转JPG")
    batch_convert_webp_to_jpg(ECCO["IMAGE_DIR_download"], r"D:\TB\Products\ECCO\document\processed_images")
    process_images_in_folder(r"D:\TB\Products\ECCO\document\processed_images", r"D:\TB\Products\ECCO\document\square_images")

    print("图片抖动，水平翻转")
    batch_process_images(Path("D:/TB/Products/ecco/document/square_images"),ECCO["IMAGE_DIR_defence"])




if __name__ == "__main__":
    main()