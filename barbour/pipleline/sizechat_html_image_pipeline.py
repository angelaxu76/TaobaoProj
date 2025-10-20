from helper.HtmlToPGNBatch import html_to_image
from helper.cutterAllsiderSpace import run_cutter_pipeline

def sizechat_html_image():
    html_to_image(r"C:\Users\martin\Downloads", r"D:\TB\HTMLToImage\output")
    run_cutter_pipeline(r"D:\TB\HTMLToImage\output", r"D:\TB\HTMLToImage\barbour_sizechat")

if __name__ == "__main__":
    sizechat_html_image()