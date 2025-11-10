from pathlib import Path
from config import CLARKS_JINGYA
from common_taobao.publication.generate_html import generate_html_from_codes_files
from common_taobao.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from helper.image.crop_to_square import run_crop_and_expand
from helper.image.copy_images import copy_images
from brands.clarks_Jingya.download_product_images import download_images_by_code_file,download_all_images_from_product_links
from brands.camper.helpers_local.image_defender_with_flip import batch_process_images

def main():
    code_file_path = r"D:\TB\Products\clarks_jingya\repulibcation\publication_codes.txt"


    print("下载指定商品编码的的图片")
    download_images_by_code_file(code_file_path)

    print("下载所有商品图片")
    # download_all_images_from_product_links()

    print("图抖动加上水平翻转")
    INPUT_DIR = Path(CLARKS_JINGYA["IMAGE_DOWNLOAD"])
    OUTPUT_DIR = Path(CLARKS_JINGYA["IMAGE_PROCESS"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_process_images(INPUT_DIR,OUTPUT_DIR)

    print("最大化灰度裁剪图片")
    bg_color = (240, 240, 240)
    tolerance = 35
    quality = 85
    run_crop_and_expand(CLARKS_JINGYA["IMAGE_PROCESS"], CLARKS_JINGYA["IMAGE_CUTTER"], bg_color, tolerance, quality)


    print("将处理好的图片copy到document目录")
    copy_images(CLARKS_JINGYA["IMAGE_CUTTER"],CLARKS_JINGYA["IMAGE_DIR"])


    print("将图片merge到一张图片中")
    batch_merge_images(CLARKS_JINGYA["IMAGE_CUTTER"],CLARKS_JINGYA["MERGED_DIR"], width=750)



    print("生成产品详情卡HTML")
    generate_html_from_codes_files("clarks_jingya",code_file_path)
    generate_first_page_from_codes_files("clarks_jingya",code_file_path)

    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    convert_html_to_images(CLARKS_JINGYA["HTML_DIR_DES"], CLARKS_JINGYA["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(CLARKS_JINGYA["HTML_IMAGE_DES"],CLARKS_JINGYA["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(CLARKS_JINGYA["HTML_DIR_FIRST_PAGE"], CLARKS_JINGYA["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(CLARKS_JINGYA["HTML_IMAGE_FIRST_PAGE"],CLARKS_JINGYA["HTML_CUTTER_FIRST_PAGE"])

    # print("导出发布商品的价格")
    # export_channel_price_excel_from_txt("clarks_jingya",code_file_path)


if __name__ == "__main__":
    main()