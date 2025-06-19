import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from config import GEOX, ensure_all_dirs

# === 配置 ===
PRODUCT_LINK_FILE = GEOX["LINKS_FILE"]
IMAGE_OUTPUT_DIR = GEOX["IMAGE_DIR"]
CHROMEDRIVER_PATH = GEOX["CHROMEDRIVER_PATH"]
WAIT = 2
DELAY = 0.5
SKIP_EXISTING_IMAGE = True

ensure_all_dirs(IMAGE_OUTPUT_DIR)

def create_driver():
    options = Options()
    options.add_argument("--headless")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

def download_image(url, path):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"🖼️ 已保存: {path.name}")
        else:
            print(f"⚠️ 图片获取失败: {url}")
    except Exception as e:
        print(f"❌ 下载失败: {e}")

def process_image_download(url, driver):
    driver.get(url)
    time.sleep(WAIT)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    code_tag = soup.select_one("span.product-id")
    if not code_tag:
        print("⚠️ 未找到编码，跳过")
        return
    code = code_tag.text.strip()

    image_divs = soup.select("div.product-images div.product-image img")
    for idx, img in enumerate(image_divs):
        src = img.get("data-src")
        if not src or "1024x1024" not in src or code not in src:
            continue
        highres_url = src.replace("1024x1024", "2048x2048")
        suffix_match = re.search(r"_([0-9]{2})\.jpg", src)
        suffix = suffix_match.group(1) if suffix_match else f"{idx}"
        filename = f"{code}_{suffix}.jpg"
        img_path = IMAGE_OUTPUT_DIR / filename

        if SKIP_EXISTING_IMAGE and img_path.exists():
            print(f"✅ 跳过已存在: {img_path.name}")
            continue
        download_image(highres_url, img_path)

def main():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return
    urls = [line.strip() for line in PRODUCT_LINK_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"📦 共 {len(urls)} 个商品待下载图片")

    driver = create_driver()
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] 下载图片: {url}")
        try:
            process_image_download(url, driver)
        except Exception as e:
            print(f"❌ 下载失败: {url} → {e}")
    driver.quit()
    print("\n✅ 所有商品图片下载完成。")

if __name__ == "__main__":
    main()