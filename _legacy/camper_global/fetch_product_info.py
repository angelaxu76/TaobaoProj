from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import os
import re
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import CAMPER_GLOBAL
from common_taobao.ingest.txt_writer import format_txt

CHROMEDRIVER_PATH = CAMPER_GLOBAL["CHROMEDRIVER_PATH"]
PRODUCT_URLS_FILE = CAMPER_GLOBAL["LINKS_FILE"]
SAVE_PATH = CAMPER_GLOBAL["TXT_DIR"]
MAX_WORKERS = 6

os.makedirs(SAVE_PATH, exist_ok=True)

def infer_gender_from_url(url: str) -> str:
    url = url.lower()
    if "/women/" in url:
        return "女款"
    elif "/men/" in url:
        return "男款"
    elif "/kids/" in url or "/children/" in url:
        return "童款"
    return "未知"

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

def process_product_url(PRODUCT_URL):
    try:
        driver = get_driver()
        print(f"\n🔍 正在访问: {PRODUCT_URL}")
        driver.get(PRODUCT_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        title_tag = soup.find("title")
        product_title = re.sub(r"\s*[-–—].*", "", title_tag.text.strip()) if title_tag else "Unknown Title"

        script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
        if not script_tag:
            print("⚠️ 未找到 JSON 数据")
            return

        json_data = json.loads(script_tag.string)
        data = json_data["props"]["pageProps"]["productSheet"]

        product_code = data.get("code", "Unknown_Code")

        product_url = PRODUCT_URL
        description = data.get("description", "")
        price_info = data.get("prices", {})
        original_price = price_info.get("previous", 0)
        discount_price = price_info.get("current", 0)

        color_data = data.get("color", "")
        color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)
        materials = data.get("materials", [])

        upper_material = "No Data"
        features = data.get("features") or []
        for feature in features:
            name = (feature.get("name") or "").lower()
            if "upper" in name:
                raw_html = feature.get("value") or ""
                upper_material = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
                break

        size_map = {}
        size_detail = {}
        for size in data.get("sizes", []):
            value = size.get("value", "").strip()
            available = size.get("available", False)
            quantity = size.get("quantity", 0)
            ean = size.get("ean", "")
            size_map[value] = "有货" if available else "无货"
            size_detail[value] = {
                "stock_count": quantity,
                "ean": ean
            }

        gender = infer_gender_from_url(PRODUCT_URL)

        info = {
            "Product Code": product_code,
            "Product Name": product_title,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": str(original_price),
            "Adjusted Price": str(discount_price),
            "Product Material": upper_material,
            "SizeMap": size_map,
            "SizeDetail": size_detail,
            "Source URL": product_url
        }

        # === 提取国家码并构造文件名 ===
        match = re.search(r"/en_([A-Z]{2})/", PRODUCT_URL)
        country_code = match.group(1) if match else "XX"
        filename = f"{product_code}_{country_code}.txt"
        filepath = SAVE_PATH / filename

        format_txt(info, filepath, brand="camper")
        print(f"✅ 已保存：{filepath.name}")

    except Exception as e:
        print(f"❌ 错误: {PRODUCT_URL} - {e}")

def main():
    with open(PRODUCT_URLS_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_product_url, url) for url in urls]
        for future in as_completed(futures):
            future.result()

if __name__ == "__main__":
    main()
