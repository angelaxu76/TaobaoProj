from helper.cutterAllsiderSpace import trim_sides_batch
from pathlib import Path
from helper.HtmlToPGNBatch import process_html_folder
from helper.splite_image_by_size import split_image_by_size
from helper.image_expand_square_add_product_code import process_images

def main():
    HTML_FOLDER = Path(r"D:/TB/HTMLToImage/input")
    OUTPUT_FOLDER = Path(r"D:/TB/HTMLToImage/output")
    CUTTER_FOLDER = Path(r"D:/TB/HTMLToImage/cutter")
    SPLIT_FOLDER = Path(r"D:/TB/HTMLToImage/split")

    print("将html转JPG")
    # process_html_folder(HTML_FOLDER,OUTPUT_FOLDER)

    print("将JPG切白边")
   #  result = trim_sides_batch(OUTPUT_FOLDER,CUTTER_FOLDER)

    print("将JPG按长度切分")
   #  split_image_by_size(CUTTER_FOLDER,SPLIT_FOLDER,1900)

    process_images(
        input_dir=r"C:\Users\martin\Downloads",
        output_dir=r"D:\TB\Products\barbour\images",
        product_code="LQU1867BK91",
    )

 
    # process_images(
    #     input_dir=r"C:\Users\martin\Downloads",
    #     output_dir=r"D:\TB\Products\barbour\images",
    #     product_code="LQU1856GN91",
    #     defend=True,                 # 是否做扰动
    #     watermark=True,              # 是否加水印
    #     wm_text="英国哈梅尔百货",           # 斜纹文字水印
    #     wm_logo_text="英国哈梅尔百货"       # 右下角小文字水印
    # )


if __name__ == "__main__":
        main()