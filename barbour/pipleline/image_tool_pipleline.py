from helper.cutterAllsiderSpace import trim_sides_batch
from pathlib import Path
from helper.HtmlToPGNBatch import process_html_folder
from helper.splite_image_by_size import split_image_by_size

def main():
    HTML_FOLDER = Path(r"D:/TB/HTMLToImage/input")
    OUTPUT_FOLDER = Path(r"D:/TB/HTMLToImage/output")
    CUTTER_FOLDER = Path(r"D:/TB/HTMLToImage/cutter")
    SPLIT_FOLDER = Path(r"D:/TB/HTMLToImage/split")

    print("将html转JPG")
    process_html_folder(HTML_FOLDER,OUTPUT_FOLDER)

    print("将JPG切白边")
    result = trim_sides_batch(OUTPUT_FOLDER,CUTTER_FOLDER)

    print("将JPG按长度切分")
    split_image_by_size(CUTTER_FOLDER,SPLIT_FOLDER,1900)



if __name__ == "__main__":
        main()