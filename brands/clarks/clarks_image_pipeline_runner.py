from brands.clarks.download_images_only import  download_images_by_code_file
from common_taobao.tools.image_defender_leftright import batch_process_images
from common_taobao.tools.crop_gray_to_square import run_crop_and_expand
from config import CLARKS
from pathlib import Path

def main():
    print("下载指定商品编码的的图片")
    #download_images_by_code_file(r"D:\TB\Products\clarks\repulibcation\五小剑\missing_images.txt")

    print("图抖动加上水平翻转")
    batch_process_images(CLARKS["IMAGE_DOWNLOAD"],CLARKS["IMAGE_PROCESS"])




    print("最大化灰度裁剪图片")
    bg_color = (240, 240, 240)
    tolerance = 35
    quality = 85

    run_crop_and_expand(CLARKS["IMAGE_PROCESS"], CLARKS["IMAGE_CUTTER"], bg_color, tolerance, quality)


if __name__ == "__main__":
    main()