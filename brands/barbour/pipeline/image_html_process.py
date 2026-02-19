from pathlib import Path
from brands.barbour.image.copy_images_by_excel import prepare_images_for_publication,rebuild_all_products_images,collect_all_images_to_flat_dir,watermark_index_0_9_inplace
from cfg.brands.barbour import BARBOUR
from common_taobao.publication.generate_html import generate_html_from_codes_files
from common_taobao.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch

import os

def main():
    code_file_path = r"D:\TB\Products\barbour\repulibcation\codes.txt"


    # excel_path = r"D:\TB\Products\barbour\document\publication\barbour_publication_20260215_144753.xlsx"
    # downloaded_dir = r"D:\TB\Products\barbour\images_download"
    # processed_dir = r"D:\TB\Products\barbour\images"
    # publish_ready_dir = r"D:\TB\Products\barbour\repulibcation\images_selected"
    # publish_need_process_dir = r"D:\TB\Products\barbour\repulibcation\need_edit"
    # missing_txt_path = r"D:\TB\Products\barbour\repulibcation\missing_codes.txt"

    # ready, need_edit, missing = prepare_images_for_publication(
    #     excel_path=excel_path,
    #     downloaded_dir=downloaded_dir,
    #     processed_dir=processed_dir,
    #     publish_ready_dir=publish_ready_dir,
    #     publish_need_process_dir=publish_need_process_dir,
    #     missing_txt_path=missing_txt_path,
    #     verbose=True,
    # )
    


    flat_images_dir=BARBOUR["IMAGE_PROCESS"]
    target_root = r"D:\TB\Products\barbour\repulibcation\images_selected"

    rebuild_all_products_images(target_root, verbose=True)

    collect_all_images_to_flat_dir(
        target_root,
        flat_images_dir,
        verbose=True,
    )

    watermark_index_0_9_inplace(
    flat_images_dir,
    watermark_text="英国哈梅尔百货",
    )



    print("将图片merge到一张图片中")
    batch_merge_images(BARBOUR["IMAGE_PROCESS"],BARBOUR["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("barbour",code_file_path,max_workers=2)
    generate_first_page_from_codes_files("barbour",code_file_path)

    # GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    convert_html_to_images(BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_DES"],BARBOUR["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"],BARBOUR["HTML_CUTTER_FIRST_PAGE"])



if __name__ == "__main__":
        main()