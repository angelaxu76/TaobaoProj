import time
import re
import json
from bs4 import BeautifulSoup
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ECCO, ensure_all_dirs
from common_taobao.txt_writer import format_txt

# ========== 全局路径 & 参数 ==========
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
TXT_DIR = ECCO["TXT_DIR"]
CHROMEDRIVER_PATH = ECCO["CHROMEDRIVER_PATH"]
MAX_THREADS = 5
WAIT = 2

# ✅ 确保目录存在
ensure_all_dirs(TXT_DIR)

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

def size_to_eu(uk_size):
    uk_to_eu = {
        "2.5-3": "35", "3.5-4": "36", "4.5": "37", "5-5.5": "38",
        "6": "39", "6.5-7": "40", "7.5": "41", "8-8.5": "42",
        "9-9.5": "43", "10": "44", "10.5-11": "45", "11.5": "46"
    }
    return uk_to_eu.get(uk_size)

def extract_sizes_and_stock_status(soup):
    results = []
    size_div = soup.find("div", class_="size-picker__rows")
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

def extract_price_info(html):
    try:
        match = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if not match:
            return None, None
        json_text = match.group(1).replace("&quot;", '"')
        data = json.loads(json_text)
        return f"{data.get('Price', 0):.2f}", f"{data.get('AdjustedPrice', 0):.2f}"
    except:
        return None, None

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

        name = soup.select_one("span.product_info__intro-title").text.strip()
        color_name = soup.select_one("span.product_info__color--selected").text.strip()
        description = soup.select_one("div.product-description").text.strip()
        short_info = soup.select_one("span.product_info__intro-class")
        gender_text = short_info.text.lower() if short_info else ""
        gender = "男款" if "men" in gender_text else "女款" if "women" in gender_text else "童款"

        original_price, discount_price = extract_price_info(driver.page_source)
        sizes = extract_sizes_and_stock_status(soup)

        info = {
            "product_code": formatted_code,
            "product_name": name,
            "original_price": original_price,
            "discount_price": discount_price,
            "color": color_name,
            "gender": gender,
            "product_url": url,
            "product_description": description,
            "size_stock": sizes
        }

        txt_path = TXT_DIR / f"{formatted_code}.txt"
        format_txt(info, txt_path)
        print(f"📄 写入: {txt_path.name}")

    except Exception as e:
        print(f"❌ 错误: {url} - {e}")
    finally:
        if driver:
            driver.quit()

def fetch_product_details():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 缺少商品链接文件: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    print(f"📦 共需处理商品: {total} 条")

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(process_product, url, i + 1, total) for i, url in enumerate(urls)]
        for _ in as_completed(futures):
            pass
    print("\n✅ ECCO 商品信息提取完毕（统一格式）")

if __name__ == "__main__":
    fetch_product_details()