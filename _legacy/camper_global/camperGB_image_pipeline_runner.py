from _legacy.camper_global.download_images_only import download_camper_images
from _legacy.camper_global.ResizeImage import expand_images_in_folder
from config import CAMPER_GLOBAL


def main():
    print("下载指定商品编码的的图片")
    #download_images_by_code_file(r"D:\TB\Products\clarks\repulibcation\五小剑\missing_images.txt")

    print("下载product_link中包含商品编码URL的图片")
    download_camper_images()

    print("图抖动加上水平翻转")
    #batch_process_images(CAMPER_GLOBAL["IMAGE_DOWNLOAD"],CAMPER_GLOBAL["IMAGE_PROCESS"])

    input_folder = CAMPER_GLOBAL["IMAGE_PROCESS"]
    output_folder = CAMPER_GLOBAL["image_cutter"]

    expand_images_in_folder(input_folder, output_folder)


if __name__ == "__main__":
    main()