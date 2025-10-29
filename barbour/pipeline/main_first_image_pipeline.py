from helper.image.trim_sides_batch import trim_sides_batch
from config import BARBOUR
from common_taobao.publication.generate_html import generate_html_from_images
from common_taobao.publication.generate_html_FristPage import generate_first_page_from_images
from helper.html.html_to_png_batch import process_html_folder

def main():

    print("图抖动加上水平翻转")

    # OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # batch_process_images(INPUT_DIR,OUTPUT_DIR)
    #
    # input_folder = BARBOUR["IMAGE_PROCESS"]
    # output_folder = BARBOUR["IMAGE_CUTTER"]
    # print("将图片变成正方形")
    # expand_images_in_folder(input_folder, output_folder)
    #
    # print("将图片merge到一张图片中")
    # batch_merge_images(CAMPER["IMAGE_CUTTER"],CAMPER["MERGED_DIR"], width=750)



    print("生成产品详情卡HTML")
    generate_html_from_images("barbour")
    generate_first_page_from_images("barbour")

    print("生成产品详情卡图片")
    process_html_folder( BARBOUR["HTML_DIR_DES"], BARBOUR["HTML_IMAGE_DES"])


    result = trim_sides_batch(BARBOUR["HTML_IMAGE_DES"],BARBOUR["HTML_DEST"])

    print("生成产品首页图片")
    process_html_folder( BARBOUR["HTML_DIR_FIRST_PAGE"], BARBOUR["HTML_IMAGE_FIRST_PAGE"])
    result = trim_sides_batch(BARBOUR["HTML_IMAGE_FIRST_PAGE"],BARBOUR["HTML_DEST"])

if __name__ == "__main__":
    main()
