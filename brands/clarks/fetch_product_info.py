import os
import re
import json
import threading
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import CLARKS, SIZE_RANGE_CONFIG
from common_taobao.txt_writer import format_txt

CHROMEDRIVER_PATH = CLARKS["CHROMEDRIVER_PATH"]
PRODUCT_URLS_FILE = CLARKS["LINKS_FILE"]
SAVE_PATH = CLARKS["TXT_DIR"]
MAX_WORKERS = 6
BRAND = "clarks"

os.makedirs(SAVE_PATH, exist_ok=True)

# ======= 辅助函数 ========
def infer_gender_from_url(url: str) -> str:
    url = url.lower()
    if "/women/" in url:
        return "女款"
    elif "/men/" in url:
        return "男款"
    elif "/kids/" in url:
        return "童款"
    return "未知"

def supplement_sizes(size_map_raw, gender, brand=BRAND):
    full_sizes = SIZE_RANGE_CONFIG.get(brand, {}).get(gender, [])
    supplemented = {}
    for size in full_sizes:
        supplemented[size] = size_map_raw.get(size, "无货")
    return supplemented

# ======= Selenium 驱动配置 ========
def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    service = Service(CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

thread_local = threading.local()
def get_driver():
    if not hasattr(thread_local, "driver"):
        thread_local.driver = create_driver()
    return thread_local.driver

# ======= 主处理函数 ========
def process_product_url(PRODUCT_URL):
    try:
        driver = get_driver()
        print(f"\n🔍 正在访问: {PRODUCT_URL}")
        driver.get(PRODUCT_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))

        soup = BeautifulSoup(driver.page_source, "html.parser")
        title_tag = soup.find("title")
        product_title = re.sub(r"\s*[-–—].*", "", title_tag.text.strip()) if title_tag else "Unknown Title"

        script_tag = soup.find("script", text=re.compile("window\.__PRELOADED_STATE__"))
        if not script_tag:
            print("⚠️ 未找到商品 JSON 数据")
            return

        json_text = re.search(r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;", script_tag.string, re.DOTALL)
        if not json_text:
            print("⚠️ 无法解析 JSON 内容")
            return

        data = json.loads(json_text.group(1))
        product_data = data.get("product", {})

        product_code = product_data.get("code", "Unknown")
        product_url = PRODUCT_URL
        description = product_data.get("description", "")

        price_info = product_data.get("price", {})
        original_price = price_info.get("was", 0)
        discount_price = price_info.get("now", 0)

        color = product_data.get("colour", {}).get("label", "")

        # 提取尺码与库存状态
        size_map = {}
        for el in soup.select(".product-sizes li"):
            size_text = el.get_text(strip=True)
            class_attr = el.get("class", [])
            available = "unavailable" not in class_attr
            size_map[size_text] = "有货" if available else "无货"

        gender = infer_gender_from_url(PRODUCT_URL)
        size_map = supplement_sizes(size_map, gender)

        info = {
            "Product Code": product_code,
            "Product Name": product_title,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": str(original_price),
            "Adjusted Price": str(discount_price),
            "Product Material": "No Data",
            "Feature": "No Data",
            "SizeMap": size_map,
            "Source URL": product_url
        }

        filepath = SAVE_PATH / f"{product_code}.txt"
        format_txt(info, filepath, brand=BRAND)
        print(f"✅ 完成 TXT: {filepath.name}")

    except Exception as e:
        print(f"❌ 错误: {PRODUCT_URL} - {e}")

# ======= 主入口 ========
def main():
    with open(PRODUCT_URLS_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_product_url, url) for url in urls]
        for future in as_completed(futures):
            future.result()

if __name__ == "__main__":
    main()
