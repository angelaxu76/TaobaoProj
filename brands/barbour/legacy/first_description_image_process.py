from config import BARBOUR
from pathlib import Path
from brands.camper.download_product_images import download_images_from_codes
from brands.camper.helpers_local.image_defender_with_flip import batch_process_images
from brands.camper.helpers_local.ResizeImage import expand_images_in_folder
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch


def main():
    print("将图片merge到一张图片中")
    code_file_path = r"D:\TB\Products\barbour\publication\codes.txt"
    # batch_merge_images(BARBOUR["IMAGE_PROCESS"],BARBOUR["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("barbour",code_file_path)
    generate_first_page_from_codes_files("barbour",code_file_path)

    print("生成产品详情卡图片")
    convert_html_to_images(BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_DES"],BARBOUR["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"],BARBOUR["HTML_CUTTER_FIRST_PAGE"])




if __name__ == "__main__":
    main()