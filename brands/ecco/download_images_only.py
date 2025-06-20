import time
import re
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config import ECCO, ensure_all_dirs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 配置 ===
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = ECCO["IMAGE_DIR"]
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
WAIT = 0
DELAY = 0
SKIP_EXISTING_IMAGE = True
MAX_WORKERS = 5  # 并发线程数

# 确保目录存在
ensure_all_dirs(IMAGE_DIR)

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)

def download_images_from_soup(soup, formatted_code):
    for img in soup.select("div.product_details__media-item-img img"):
        if "src" not in img.attrs:
            continue
        img_url = img["src"].replace("DetailsMedium", "ProductDetailslarge3x")
        match = re.search(r'/([0-9A-Za-z-]+-(?:o|m|b|s|top_left_pair|front_pair))\.webp', img_url)
        img_code = match.group(1) if match else formatted_code
        img_path = IMAGE_DIR / f"{img_code}.webp"

        if SKIP_EXISTING_IMAGE and img_path.exists():
            print(f"✅ 跳过: {img_path.name}")
            continue

        try:
            with open(img_path, "wb") as f:
                f.write(requests.get(img_url, timeout=10).content)
            print(f"🖼️ 下载: {img_path.name}")
            time.sleep(DELAY)
        except Exception as e:
            print(f"❌ 下载失败: {img_url} - {e}")

def process_image_url(url):
    driver = None
    try:
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        code_info = soup.find('div', class_='product_info__product-number')
        if not code_info:
            print(f"⚠️ 未找到编码，跳过: {url}")
            return

        product_code = code_info.text.strip().split()[2]
        code, color = product_code[:6], product_code[6:]
        formatted_code = f"{code}-{color}"

        download_images_from_soup(soup, formatted_code)

    except Exception as e:
        print(f"❌ 商品处理失败: {url} - {e}")
    finally:
        if driver:
            driver.quit()

def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 未找到链接文件: {PRODUCT_LINKS_FILE}")
        return
    url_list = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"\n📸 开始下载 {len(url_list)} 个商品的图片...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_url, url) for url in url_list]
        for future in as_completed(futures):
            pass  # 每个线程已自行打印日志

    print("\n✅ 所有图片下载完成。")

if __name__ == "__main__":
    main()
