import os
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from PIL import Image
import time

# 设置参数
HTML_FOLDER = "D:/TB/HTMLToImage/input"  # HTML 文件夹路径
OUTPUT_FOLDER = "D:/TB/HTMLToImage/output"   # 输出图片文件夹
GECKODRIVER_PATH = r"D:\Software\geckodriver.exe"  # GeckoDriver 路径


def trim_image(image_path):
    """去除图片左右空白区域"""
    image = Image.open(image_path)
    image = image.convert("RGB")
    bbox = image.getbbox()  # 获取内容区域
    cropped_image = image.crop(bbox)
    cropped_image.save(image_path)
    print(f'Trimmed image saved as {image_path}')


def html_to_full_screenshot(html_path, output_image, geckodriver_path):
    # 配置 Firefox WebDriver
    firefox_options = Options()
    firefox_options.add_argument('--headless')  # 运行无头模式

    # 启动 Firefox WebDriver
    service = Service(geckodriver_path)
    driver = webdriver.Firefox(service=service, options=firefox_options)

    # 打开 HTML 文件
    driver.get(f'file://{html_path}')

    # 等待页面加载完成
    time.sleep(2)

    # 获取完整页面截图
    driver.get_full_page_screenshot_as_file(output_image)

    # 关闭 WebDriver
    driver.quit()

    # 裁剪图片
    trim_image(output_image)


def process_html_folder(html_folder, output_folder, geckodriver_path):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for file in os.listdir(html_folder):
        if file.endswith(".html"):
            html_path = os.path.join(html_folder, file)
            output_image = os.path.join(output_folder, f"{os.path.splitext(file)[0].replace('_', '')}_Detail.png")
            print(f'Processing {html_path}...')
            html_to_full_screenshot(html_path, output_image, geckodriver_path)


# 执行批量转换
process_html_folder(HTML_FOLDER, OUTPUT_FOLDER, GECKODRIVER_PATH)
