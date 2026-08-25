import shutil
from config import REISS
from pathlib import Path
from brands.camper.helpers_local.ResizeImage import expand_images_in_folder
from common.publication.generate_html import generate_html_from_codes_files
from common.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch
from ops.image_rename.rename_by_shot_priority import rename_by_shot_priority
from brands.reiss.core.download_reiss_images import download_reiss_images_from_codes


def main():
    code_file_path = r"D:\TB\Products\reiss\repulibcation\publication_codes_outerwear.txt"


    print("\n🟡 Step: 4️⃣ 下载指定编码的图片")
    sample_codes_file = Path(r"D:\TB\Products\reiss\repulibcation\publication_codes_outerwear.txt")
    download_reiss_images_from_codes(sample_codes_file)

    input_folder = REISS["IMAGE_DOWNLOAD"]
    output_folder = REISS["IMAGE_CUTTER"]
    print("将图片变成正方形")
    expand_images_in_folder(input_folder, output_folder)

    print("将图片merge到一张图片中")
    batch_merge_images(REISS["IMAGE_DOWNLOAD"],REISS["MERGED_DIR"], width=750)

    print("图片从download拷贝到document下面")
    shutil.copytree(REISS["IMAGE_DOWNLOAD"], REISS["IMAGE_DIR"], dirs_exist_ok=True)

    print("原样拷贝到 IMAGE_PROCESS（供生成详情页/首页封面图使用）")
    shutil.copytree(REISS["IMAGE_DOWNLOAD"], REISS["IMAGE_PROCESS"], dirs_exist_ok=True)

    print("按优先级把 IMAGE_PROCESS 里的图片改名为 __1/__2/...")
    rename_by_shot_priority(REISS["IMAGE_PROCESS"], brand="reiss")

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("reiss",code_file_path)
    generate_first_page_from_codes_files("reiss",code_file_path)

    # print("生成产品详情卡图片")
    convert_html_to_images(REISS["HTML_DIR_DES"], REISS["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(REISS["HTML_IMAGE_DES"],REISS["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(REISS["HTML_DIR_FIRST_PAGE"], REISS["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(REISS["HTML_IMAGE_FIRST_PAGE"],REISS["HTML_CUTTER_FIRST_PAGE"])


if __name__ == "__main__":
    main()
