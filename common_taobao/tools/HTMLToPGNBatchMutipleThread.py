import os
import time
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from PIL import Image


def trim_image(image_path):
    """去除图片左右空白区域"""
    image = Image.open(image_path)
    image = image.convert("RGB")
    bbox = image.getbbox()
    if bbox:
        cropped_image = image.crop(bbox)
        cropped_image.save(image_path)
        print(f'[Trimmed] {image_path}')
    else:
        print(f'[Skipped] No bounding box for {image_path}')


def html_to_full_screenshot(html_path, output_image, geckodriver_path):
    """使用 Selenium 截取 HTML 页面截图"""
    firefox_options = Options()
    firefox_options.add_argument('--headless')  # 无头模式

    service = Service(geckodriver_path)
    driver = webdriver.Firefox(service=service, options=firefox_options)

    try:
        driver.get(f'file://{html_path}')
        time.sleep(2)
        driver.get_full_page_screenshot_as_file(output_image)
        print(f'[Saved] {output_image}')
    except Exception as e:
        print(f'[Error] {html_path}: {e}')
    finally:
        driver.quit()

    trim_image(output_image)


def process_html_file(file, html_folder, output_folder, geckodriver_path):
    """处理单个 HTML 文件"""
    if file.endswith(".html"):
        html_path = os.path.join(html_folder, file)
        output_image = os.path.join(output_folder, f"{os.path.splitext(file)[0].replace('_', '')}_Detail.png")
        html_to_full_screenshot(html_path, output_image, geckodriver_path)


def convert_html_to_images(input_dir, output_dir, geckodriver_path, max_workers=4):
    """
    将 HTML 转换为图片（支持多线程）

    :param input_dir: HTML 文件夹
    :param output_dir: 输出图片文件夹
    :param geckodriver_path: GeckoDriver 路径
    :param max_workers: 最大线程数
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    html_files = [f for f in os.listdir(input_dir) if f.endswith(".html")]
    print(f"[Info] Found {len(html_files)} HTML files.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for file in html_files:
            executor.submit(process_html_file, file, input_dir, output_dir, geckodriver_path)

    print(f"[Done] All screenshots saved to {output_dir}")
