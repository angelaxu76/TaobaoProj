from config import CAMPER
from pathlib import Path
from brands.camper.download_product_images import download_images_from_codes
from brands.camper.helpers_local.image_defender_with_flip import batch_process_images
from brands.camper.helpers_local.ResizeImage import expand_images_in_folder
from common_taobao.publication.generate_html import generate_html_from_codes_files
from common_taobao.publication.generate_html_FristPage import generate_first_page_from_codes_files
from helper.image.merge_product_images import batch_merge_images
from helper.html.html_to_png_multithread import convert_html_to_images
from helper.image.trim_sides_batch import trim_sides_batch


def main():
    print("下载product_link中包含商品编码URL的图片")
    # download_camper_images()

    code_file_path = r"D:\TB\Products\camper\repulibcation\publication_codes.txt"
    print("检查哪些图片缺少，TXT中编码但图片文件夹中没有图片")
    # check_missing_images("camper")


    print("下载指定商品编码的的图片")
    download_images_from_codes(code_file_path)

    print("图抖动加上水平翻转")
    INPUT_DIR = Path(CAMPER["IMAGE_DOWNLOAD"])
    OUTPUT_DIR = Path(CAMPER["IMAGE_PROCESS"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_process_images(INPUT_DIR,OUTPUT_DIR)

    input_folder = CAMPER["IMAGE_PROCESS"]
    output_folder = CAMPER["IMAGE_CUTTER"]
    print("将图片变成正方形")
    expand_images_in_folder(input_folder, output_folder)

    print("将图片merge到一张图片中")
    batch_merge_images(CAMPER["IMAGE_CUTTER"],CAMPER["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_codes_files("camper",code_file_path,max_workers=2)
    generate_first_page_from_codes_files("camper",code_file_path)

    # GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    convert_html_to_images(CAMPER["HTML_DIR_DES"], CAMPER["HTML_IMAGE_DES"],"",6)
    trim_sides_batch(CAMPER["HTML_IMAGE_DES"],CAMPER["HTML_CUTTER_DES"])

    print("生成产品首页图片")
    convert_html_to_images(CAMPER["HTML_DIR_FIRST_PAGE"], CAMPER["HTML_IMAGE_FIRST_PAGE"],"",6)
    trim_sides_batch(CAMPER["HTML_IMAGE_FIRST_PAGE"],CAMPER["HTML_CUTTER_FIRST_PAGE"])

    print("导出发布商品的价格")
    code_file_path = r"D:\TB\Products\camper\repulibcation\publication_codes.txt"
    code_missing_path = r"D:\TB\Products\camper\repulibcation\publication_codes_missing.txt"
    

    # export_channel_price_excel_from_txt("camper",code_file_path)
    # code_missing_path = r"D:\TB\Products\camper\repulibcation\publication_codes_missing.txt"
    # export_channel_price_excel_from_channel_ids("camper",code_missing_path)


if __name__ == "__main__":
    main()
