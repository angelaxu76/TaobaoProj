from brands.camper.download_images_only import download_images_from_codes,download_camper_images
from brands.camper.image.image_defender_with_flip import batch_process_images
from brands.camper_global.ResizeImage import expand_images_in_folder
from config import CAMPER
from pathlib import Path

def main():
    print("下载指定商品编码的的图片")
    #download_images_from_codes(r"D:\TB\Products\camper\repulibcation\missing_images.txt")

    print("下载product_link中包含商品编码URL的图片")
    #download_camper_images()

    print("图抖动加上水平翻转")
    #batch_process_images()

    input_folder = CAMPER["IMAGE_PROCESS"]
    output_folder = CAMPER["IMAGE_CUTTER"]

    expand_images_in_folder(input_folder, output_folder)


if __name__ == "__main__":
    main()