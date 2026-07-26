"""
GEOX 商品图流水线 — step 3：合并图片 + 生成详情页/首页 HTML 和图片。

图片来自两个目录：
  - GEOX["IMAGE_CUTTER"]   —— step1 里 run_crop_and_expand 的输出（方形图）
  - GEOX["IMAGE_ROTATED"]  —— step2 AI 视角旋转的输出
batch_merge_images 支持传入多个输入目录（列表），会把两边同一个商品编码的
图片合并到一起再拼图，不需要手动把两个目录的文件挪到一起。
"""
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.image.copy_images import copy_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from config import GEOX

CODE_FILE_PATH = r"D:\TB\Products\geox\repulibcation\publication_codes.txt"


def main():
    print("将处理好的图片copy到document目录")
    copy_images(GEOX["IMAGE_CUTTER"], GEOX["IMAGE_DIR"])

    print("将图片merge到一张图片中")
    batch_merge_images([GEOX["IMAGE_CUTTER"], GEOX["IMAGE_ROTATED"]], GEOX["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("GEOX", CODE_FILE_PATH)
    generate_first_page_from_codes_files("GEOX", CODE_FILE_PATH)

    print("生成产品详情卡图片")
    convert_html_to_images(GEOX["HTML_DIR_DES"], GEOX["HTML_IMAGE_DES"], "", 6)
    trim_sides_batch(GEOX["HTML_IMAGE_DES"], GEOX["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(GEOX["HTML_DIR_FIRST_PAGE"], GEOX["HTML_IMAGE_FIRST_PAGE"], "", 6)
    trim_sides_batch(GEOX["HTML_IMAGE_FIRST_PAGE"], GEOX["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
