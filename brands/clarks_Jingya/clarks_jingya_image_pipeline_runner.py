from brands.clarks_Jingya.download_images_only import  download_images_by_code_file,download_all_images_from_product_links
from common_taobao.tools.image_defender_leftright import batch_process_images
from common_taobao.tools.crop_gray_to_square import run_crop_and_expand
from common_taobao.tools.merge_product_images import batch_merge_images
from common_taobao.tools.HTMLToPGNBatchMutipleThread import convert_html_to_images
from common_taobao.tools.cutterAllsiderSpace import trim_images_in_folder
from common_taobao.tools.copy_images import copy_images
from common_taobao.generate_html import main as generate_html_main
from config import CLARKS_JINGYA
from pathlib import Path

def main():
    print("下载指定商品编码的的图片")
    #download_images_by_code_file(r"D:\TB\Products\clarks\repulibcation\五小剑\missing_images.txt")

    print("下载所有商品图片")
    #download_all_images_from_product_links()

    print("图抖动加上水平翻转")
    #batch_process_images(CLARKS_JINGYA["IMAGE_DOWNLOAD"],CLARKS_JINGYA["IMAGE_PROCESS"])

    print("最大化灰度裁剪图片")
    bg_color = (240, 240, 240)
    tolerance = 35
    quality = 85
    #run_crop_and_expand(CLARKS_JINGYA["IMAGE_PROCESS"], CLARKS_JINGYA["IMAGE_CUTTER"], bg_color, tolerance, quality)


    print("将处理好的图片copy到document目录")
    #copy_images(CLARKS_JINGYA["IMAGE_CUTTER"],CLARKS_JINGYA["IMAGE_DIR"])


    print("将图片merge到一张图片中")
    #batch_merge_images(CLARKS_JINGYA["IMAGE_CUTTER"], CLARKS_JINGYA["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    #generate_html_main("clarks_jingya")

    print("生成产品详情卡图片")
    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    #convert_html_to_images( CLARKS_JINGYA["HTML_DIR"], CLARKS_JINGYA["HTML_IMAGE"],GECKODRIVER_PATH, 10)

    trim_images_in_folder(CLARKS_JINGYA["HTML_IMAGE"],CLARKS_JINGYA["HTML_CUTTER"],file_pattern="*.png", tolerance=5)


if __name__ == "__main__":
    main()