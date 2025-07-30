from brands.camper.download_images_only import download_images_from_codes,download_camper_images
from brands.camper.image.image_defender_with_flip import batch_process_images
from brands.camper_global.ResizeImage import expand_images_in_folder
from common_taobao.tools.merge_product_images import batch_merge_images
from common_taobao.tools.HTMLToPGNBatchMutipleThread import convert_html_to_images
from common_taobao.tools.cutterAllsiderSpace import trim_images_in_folder
from common_taobao.generate_html import main as generate_html_main
from common_taobao.check_missing_images import check_missing_images
from config import CAMPER
from pathlib import Path

def main():
    print("检查哪些图片缺少，TXT中编码但图片文件夹中没有图片")
    check_missing_images("camper")


    print("下载指定商品编码的的图片")
    download_images_from_codes(r"D:\TB\Products\camper\repulibcation\missing_images.txt")

    print("下载product_link中包含商品编码URL的图片")
    download_camper_images()

    print("图抖动加上水平翻转")
    batch_process_images()


    input_folder = CAMPER["IMAGE_PROCESS"]
    output_folder = CAMPER["IMAGE_CUTTER"]
    print("将图片变成正方形")
    expand_images_in_folder(input_folder, output_folder)

    print("将图片merge到一张图片中")
    batch_merge_images(CAMPER["IMAGE_CUTTER"],CAMPER["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_main("camper")

    print("生成产品详情卡图片")
    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    convert_html_to_images( CAMPER["HTML_DIR"], CAMPER["HTML_IMAGE"],GECKODRIVER_PATH, 10)

    trim_images_in_folder(CAMPER["HTML_IMAGE"],CAMPER["HTML_CUTTER"],file_pattern="*.png", tolerance=5)


if __name__ == "__main__":
    main()