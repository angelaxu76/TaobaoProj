from config import GEOX
from pathlib import Path
from helper.image_defender_leftright import batch_process_images

def main():
    #下载指定编码的图片
    code_txt_path = Path(r"D:\TB\Products\geox\repulibcation\英国伦敦代购2015\missing_images.txt")
    #download_geox_images_by_code_file(code_txt_path)

    #图片抖动，水平翻转
    batch_process_images(GEOX["IMAGE_DOWNLOAD"],Path(r"D:\TB\Products\geox\document\images_def"))


if __name__ == "__main__":
    main()