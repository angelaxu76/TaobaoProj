from helper.image_defender_leftright import batch_process_images
from brands.ecco.image.ImageMaxCutter import batch_convert_webp_to_jpg,process_images_in_folder
from helper.merge_product_images import batch_merge_images
from common_taobao.generate_html import generate_html_from_codes_files
from common_taobao.generate_html_FristPage import generate_first_page_from_codes_files
from helper.HTMLToPGNBatchMutipleThread import convert_html_to_images
from helper.cutterAllsiderSpace import trim_sides_batch
from brands.ecco.download_images_only import download_images_by_code_file
from config import ECCO
from pathlib import Path


def main():
    code_file_path = r"D:\TB\Products\ecco\repulibcation\publication_codes.txt"

    print("下载指定商品编码的的图片")
    download_images_by_code_file(code_file_path)

    print("最大化裁剪，转JPG")
    process_images_in_folder(ECCO["IMAGE_DOWNLOAD"], ECCO["IMAGE_CUTTER"])

    batch_convert_webp_to_jpg(ECCO["IMAGE_DOWNLOAD"], ECCO["IMAGE_PROCESS"])

    print("图片抖动，水平翻转")
    batch_process_images(ECCO["IMAGE_CUTTER"],ECCO["IMAGE_PROCESS"])


    print("将图片merge到一张图片中")
    batch_merge_images(ECCO["IMAGE_PROCESS"],ECCO["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("ecco",code_file_path)
    generate_first_page_from_codes_files("ecco",code_file_path)

    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    convert_html_to_images(ECCO["HTML_DIR_DES"], ECCO["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(ECCO["HTML_IMAGE_DES"],ECCO["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(ECCO["HTML_DIR_FIRST_PAGE"], ECCO["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(ECCO["HTML_IMAGE_FIRST_PAGE"],ECCO["HTML_CUTTER_FIRST_PAGE"])



if __name__ == "__main__":
    main()