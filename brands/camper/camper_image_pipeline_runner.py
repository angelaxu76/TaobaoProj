from brands.camper.download_images_only import download_images_from_codes,download_camper_images
from brands.camper.image.image_defender_with_flip import batch_process_images
from brands.camper_global.ResizeImage import expand_images_in_folder
from common_taobao.tools.merge_product_images import batch_merge_images
from common_taobao.tools.HTMLToPGNBatchMutipleThread import convert_html_to_images
from common_taobao.tools.cutterAllsiderSpace import trim_images_in_folder
from common_taobao.generate_html import main as generate_html_main
from common_taobao.check_missing_images import check_missing_images
from common_taobao.generate_html_FristPage import generate_html_for_first_page
from config import CAMPER
from pathlib import Path

def main():
    print("检查哪些图片缺少，TXT中编码但图片文件夹中没有图片")
    # check_missing_images("camper")


    print("下载指定商品编码的的图片")
    # download_images_from_codes(r"D:\TB\Products\camper\repulibcation\missing_images.txt")

    print("下载product_link中包含商品编码URL的图片")
    # download_camper_images()

    print("图抖动加上水平翻转")
    INPUT_DIR = Path(CAMPER["IMAGE_DOWNLOAD"])
    OUTPUT_DIR = Path(CAMPER["IMAGE_PROCESS"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # batch_process_images(INPUT_DIR,OUTPUT_DIR)


    input_folder = CAMPER["IMAGE_PROCESS"]
    output_folder = CAMPER["IMAGE_CUTTER"]
    print("将图片变成正方形")
    # expand_images_in_folder(input_folder, output_folder)

    print("将图片merge到一张图片中")
    # batch_merge_images(CAMPER["IMAGE_CUTTER"],CAMPER["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    #generate_html_main("camper")
    #generate_html_for_first_page("camper")

    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    #convert_html_to_images( CAMPER["HTML_DIR_DES"], CAMPER["HTML_IMAGE_DES"],GECKODRIVER_PATH,"Description",10)
    trim_images_in_folder(CAMPER["HTML_IMAGE_DES"],CAMPER["HTML_CUTTER_DES"],file_pattern="*.png", tolerance=5)

    print("生成产品首页图片")
    #convert_html_to_images( CAMPER["HTML_DIR_FIRST_PAGE"], CAMPER["HTML_IMAGE_FIRST_PAGE"],GECKODRIVER_PATH, "FristPage", 10)
    #trim_images_in_folder(CAMPER["HTML_IMAGE_FIRST_PAGE"],CAMPER["HTML_CUTTER_FIRST_PAGE"],file_pattern="*.png", tolerance=5)

if __name__ == "__main__":
    main()