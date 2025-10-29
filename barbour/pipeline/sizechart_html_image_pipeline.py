from helper.html.html_to_png_batch import html_to_image
from helper.image.trim_sides_batch import run_cutter_pipeline

def sizechat_html_image():
    html_to_image(r"C:\Users\martin\Downloads", r"D:\TB\HTMLToImage\output")
    run_cutter_pipeline(r"D:\TB\HTMLToImage\output", r"D:\TB\HTMLToImage\barbour_sizechat")

if __name__ == "__main__":
    sizechat_html_image()