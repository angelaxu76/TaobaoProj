from tools.cutterAllsiderSpace import trim_sides_batch
from config import BARBOUR
from pathlib import Path
from common_taobao.generate_html import generate_html_from_images
from common_taobao.generate_html_FristPage import generate_first_page_from_images
from tools.HtmlToPGNBatch import process_html_folder

def main():

    print("图抖动加上水平翻转")

    # OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # batch_process_images(INPUT_DIR,OUTPUT_DIR)

    #input_folder = BARBOUR["IMAGE_PROCESS"]
    #output_folder = BARBOUR["IMAGE_CUTTER"]
    #print("将图片变成正方形")
    # expand_images_in_folder(input_folder, output_folder)

    # print("将图片merge到一张图片中")
    # batch_merge_images(CAMPER["IMAGE_CUTTER"],CAMPER["MERGED_DIR"], width=750)

    print("生成产品详情卡HTML")
    generate_html_from_images("barbour")
    generate_first_page_from_images("barbour")

    GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径
    print("生成产品详情卡图片")
    process_html_folder( BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"], GECKODRIVER_PATH)


    result = trim_sides_batch(
        input_dir=BARBOUR["HTML_IMAGE_DES"],
        output_dir=BARBOUR["HTML_DEST"],
        pattern="*.jpg;*.png",  # 可不传
        tolerance=5,
        recursive=False,
        overwrite=True,
        dry_run=False,
        workers=0,  # 0=自动
    )

    print("生成产品首页图片")
    process_html_folder( BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"], GECKODRIVER_PATH)
    result = trim_sides_batch(
        input_dir=BARBOUR["HTML_IMAGE_FIRST_PAGE"],
        output_dir=BARBOUR["HTML_DEST"],
        pattern="*.jpg;*.png",  # 可不传
        tolerance=5,
        recursive=False,
        overwrite=True,
        dry_run=False,
        workers=0,  # 0=自动
    )

if __name__ == "__main__":
    main()
