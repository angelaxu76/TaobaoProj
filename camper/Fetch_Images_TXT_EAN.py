import os
import re
import json
import time
import threading
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================== 配置区 ===========================
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
DEFAULT_TEXT_PATH = "D:/TB/Products/camper/publication/TXT/"
DEFAULT_IMAGE_PATH = "D:/TB/Products/camper/publication/images/"
PRODUCT_URLS_FILE = "D:/TB/Products/camper/publication/product_urls.txt"
IMAGE_BASE_URL = "https://cloud.camper.com/is/image/YnJldW5pbmdlcjAx/"
IMAGE_SUFFIXES = ['_C.jpg', '_F.jpg', '_L.jpg', '_T.jpg', '_P.jpg']

# ===================== Selenium 多线程驱动 =====================
thread_local = threading.local()

def get_driver():
    if not hasattr(thread_local, "driver"):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        options.add_argument("user-agent=Mozilla/5.0")
        service = Service(CHROMEDRIVER_PATH)
        thread_local.driver = webdriver.Chrome(service=service, options=options)
    return thread_local.driver

# ===================== 图片下载函数 =====================
def download_images(product_code, image_path):
    os.makedirs(image_path, exist_ok=True)
    for suffix in IMAGE_SUFFIXES:
        image_url = IMAGE_BASE_URL + product_code + suffix
        image_name = f"{product_code}{suffix}"
        save_path = os.path.join(image_path, image_name)
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            with open(save_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ 图片已下载: {image_name}")
        except Exception as e:
            print(f"❌ 图片下载失败: {image_url}，原因: {e}")

# ===================== 页面处理函数 =====================
def process_product_url(url, save_txt=True, download_img=False,
                        txt_path=DEFAULT_TEXT_PATH, image_path=DEFAULT_IMAGE_PATH):
    os.makedirs(txt_path, exist_ok=True)
    if download_img:
        os.makedirs(image_path, exist_ok=True)

    try:
        driver = get_driver()
        print(f"\n🔍 正在处理页面: {url}")
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
        if not script_tag:
            print(f"⚠️ 页面中未找到 JSON 数据: {url}")
            return

        data = json.loads(script_tag.string)
        sheet = data["props"]["pageProps"].get("productSheet", {})

        product_code = sheet.get("code") or "Unknown_Code"
        brand = sheet.get("brand") or "Unknown_Brand"
        description = sheet.get("description") or "No Description"
        features = sheet.get("features", [])
        care = sheet.get("careDetailsArray", [])
        materials = sheet.get("careTextArray", [])
        sizes = sheet.get("sizes", [])

        prices = sheet.get("prices")
        if isinstance(prices, dict):
            price_value = prices.get("current", "")
            currency = prices.get("currency", "")
            price = f"{price_value}{currency}"
        else:
            price = "No Price Info"

        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.text.strip()
            title = re.sub(r"\s*[-–—].*?Camper.*?$", "", title)
        else:
            title = "No Title Found"

        size_lines = []
        for s in sizes:
            label = s.get("label", "N/A")
            value = s.get("value", "N/A")
            ean = s.get("ean", "N/A")
            stock = s.get("quantity", 0)
            available = s.get("available", False)
            size_lines.append(f"尺码: {value}（{label}） | EAN: {ean} | 可用: {available} | 库存: {stock}")

        if save_txt:
            file_name = f"{product_code}.txt"
            file_path = os.path.join(txt_path, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"Product URL: {url}\n\n")
                f.write(f"Product CODE: {product_code}\n\n")
                f.write(f"Product Title: {title}\n\n")
                f.write(f"Product style: {brand}\n\n")
                f.write(f"Product price: {price}\n\n")
                f.write("Description:\n" + description + "\n\n")
                f.write("Features:\n" + json.dumps(features, ensure_ascii=False) + "\n\n")
                f.write("Product Care:\n" + json.dumps(care, ensure_ascii=False) + "\n\n")
                f.write("Product materials:\n" + json.dumps(materials, ensure_ascii=False) + "\n\n")
                f.write("Size & EAN Info:\n" + "\n".join(size_lines))
            print(f"📄 商品信息已写入: {file_path}")

        if download_img:
            download_images(product_code, image_path)

    except Exception as e:
        print(f"❌ 页面处理失败: {url}，错误: {e}")

# ===================== 主函数入口 =====================
def main(product_urls_file=PRODUCT_URLS_FILE, save_txt=True, download_img=False):
    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(process_product_url, url, save_txt, download_img) for url in urls]
        for future in as_completed(futures):
            future.result()

    print("🎯 所有商品处理完成！")

# ===================== CLI 调用入口 =====================
if __name__ == "__main__":
    main()
