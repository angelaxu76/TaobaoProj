"""
图片处理 + 产品详情 HTML/图片生成流水线。

前置条件：image_select_and_prepare.py 已运行完成（图片已整理到 IMAGE_PROCESS 目录）。

步骤：
  1. 将 IMAGE_PROCESS 中的各款图片横向合并为一张宽图（MERGED_DIR）
  2. 生成产品详情卡 HTML（含首页）
  3. 将 HTML 渲染为图片
  4. 裁剪图片两侧留白
"""
from cfg.brands.barbour import BARBOUR
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch


def main():
    code_file_path = r"D:\TB\Products\barbour\repulibcation\codes.txt"

    print("将图片 merge 到一张图片中")
    # batch_merge_images(BARBOUR["IMAGE_PROCESS"], BARBOUR["MERGED_DIR"], width=750)

    print("生成产品详情卡 HTML")
    generate_html_from_codes_files("barbour", code_file_path, max_workers=2)
    generate_first_page_from_codes_files("barbour", code_file_path)

    print("生成产品详情卡图片")
    convert_html_to_images(BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"], "", 6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_DES"], BARBOUR["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"], "", 6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"], BARBOUR["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
