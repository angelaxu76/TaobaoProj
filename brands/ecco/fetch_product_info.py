
import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ECCO, ensure_all_dirs

# ========== 全局路径 & 参数 ==========
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
TXT_DIR = ECCO["TXT_DIR"]
IMAGE_DIR = ECCO["IMAGE_DIR"]
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
MAX_THREADS = 5
WAIT = 2
DELAY = 0.5

# ✅ 确保目录存在
ensure_all_dirs(TXT_DIR, IMAGE_DIR)

# ✅ 控制选项
SKIP_EXISTING_IMAGE = True

# ========== 工具函数 ==========
def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)

def safe_get_text(soup, selector, attr=None):
    try:
        tag = soup.select_one(selector)
        if tag:
            return tag[attr].strip() if attr else tag.text.strip()
    except:
        pass
    return "No Data"

def size_to_eu(uk_size):
    uk_to_eu = {
        "2.5-3": "35", "3.5-4": "36", "4.5": "37", "5-5.5": "38",
        "6": "39", "6.5-7": "40", "7.5": "41", "8-8.5": "42",
        "9-9.5": "43", "10": "44", "10.5-11": "45", "11.5": "46"
    }
    return uk_to_eu.get(uk_size)

def extract_sizes_and_stock_status(html):
    soup = BeautifulSoup(html, "html.parser")
    size_div = soup.find("div", class_="size-picker__rows")
    results = []

    if size_div:
        for btn in size_div.find_all("button"):
            uk_size = btn.text.strip()
            eu_size = size_to_eu(uk_size)
            if not eu_size:
                continue
            is_soldout = "size-picker__item--soldout" in btn.get("class", [])
            status = "无货" if is_soldout else "有货"
            results.append(f"{eu_size}: {status}")
        return results

    for li in soup.select("div.product-description-list li"):
        text = li.text.strip()
        if "Available in European sizes" in text:
            sizes = re.findall(r"\d{2}-\d{2}", text)
            if sizes:
                results.extend([f"{s}: 默认有货" for s in sizes])
    return results

def extract_price_info(html):
    try:
        match = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if not match:
            return []
        json_text = match.group(1).replace("&quot;", '"')
        data = json.loads(json_text)
        return [f"原价: {data.get('Price', 0):.2f}", f"折扣价: {data.get('AdjustedPrice', 0):.2f}"]
    except:
        return []

def process_product(url, idx, total):
    driver = None
    try:
        print(f"\n🔍 ({idx}/{total}) 正在处理: {url}")
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        code_info = soup.find('div', class_='product_info__product-number')
        if not code_info:
            raise Exception("未找到编码")
        product_code = code_info.text.strip().split()[2]
        code, color = product_code[:6], product_code[6:]
        formatted_code = f"{code}-{color}"

        txt_path = TXT_DIR / f"{formatted_code}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Brand Name: ECCO\n")
            f.write(f"Product Code: {code}\n")
            f.write(f"Color Code: {color}\n")
            f.write("Color: {}\n".format(safe_get_text(soup, "span.product_info__color--selected")))
            f.write("Price: {}\n\n".format(safe_get_text(soup, "span[ng-bind-html='productdetailctrl.origPrice | trusted']")))
            f.write("product_title: {}\n\n".format(safe_get_text(soup, "span.product_info__intro-title")))
            f.write("product Short Info:\n{}\n\n".format(safe_get_text(soup, "span.product_info__intro-class")))
            f.write("product Short Description:\n{}\n\n".format(safe_get_text(soup, "div.product-description")))
            f.write("Product Detail Descriptions:\n")
            for i, li in enumerate(soup.select("div.product-description-list li"), 1):
                f.write(f"{i}. {li.text.strip()}\n")
            f.write("\nAvailable Sizes:\n")
            for s in extract_sizes_and_stock_status(driver.page_source):
                f.write(s + "\n")
            f.write("\nPrice Info:\n")
            for p in extract_price_info(driver.page_source):
                f.write(p + "\n")

        print(f"📄 信息保存: {txt_path.name}")

    except Exception as e:
        print(f"❌ 错误: {url} - {e}")
    finally:
        if driver:
            driver.quit()

def fetch_product_details():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 商品链接文件不存在: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    print(f"\n📦 共 {total} 条商品，线程数: {MAX_THREADS}")

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(process_product, url, i + 1, total) for i, url in enumerate(urls)]
        for _ in as_completed(futures):
            pass
    print("\n✅ ECCO 商品信息处理完毕（不含图片）！")

if __name__ == "__main__":
    fetch_product_details()
