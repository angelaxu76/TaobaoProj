
import os
import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import GEOX
from common_taobao.txt_writer import format_txt

PRODUCT_LINK_FILE = GEOX["BASE"] / "publication" / "product_links.txt"
TXT_OUTPUT_DIR = GEOX["TXT_DIR"]
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
MAX_THREADS = 15

TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=options)

def get_html(driver, url):
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.product-id"))
        )
        time.sleep(1)
        return driver.page_source
    except:
        print(f"⚠️ 页面加载失败: {url}")
        return None

def process_product(url):
    driver = create_driver()
    try:
        html = get_html(driver, url)
        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        code_tag = soup.select_one("span.product-id")
        code = code_tag.text.strip() if code_tag else "No Data"

        name_tag = soup.select_one("div.sticky-image img")
        name = name_tag["alt"].strip() if name_tag and name_tag.has_attr("alt") else "No Data"

        # 先提取价格标签
        price_tag = soup.select_one("span.product-price span.value")
        discount_tag = soup.select_one("span.sales.discount span.value")

        # 获取原始字符串
        full_price_raw = price_tag["content"].strip() if price_tag and price_tag.has_attr("content") else "No Data"
        discount_price_raw = discount_tag["content"].strip() if discount_tag and discount_tag.has_attr("content") else full_price_raw

        # 提取最大值（如 65.00-70.00 → 70.00）
        def extract_max_price(price_str):
            if "-" in price_str:
                try:
                    parts = [float(p.strip()) for p in price_str.split("-") if p.strip()]
                    return str(max(parts))
                except:
                    pass
            return price_str  # 返回原始字符串

        full_price = extract_max_price(full_price_raw)
        discount_price = extract_max_price(discount_price_raw)

        color_block = soup.select_one("div.sticky-color")
        color = color_block.get_text(strip=True).replace("Color:", "") if color_block else "No Data"

        materials_block = soup.select_one("div.materials-container")
        material_text = materials_block.get_text(" ", strip=True) if materials_block else "No Data"

        desc_block = soup.select_one("div.product-description div.value")
        description = desc_block.get_text(strip=True) if desc_block else "No Data"

        size_blocks = soup.select("div.size-value")
        size_stock = {}
        for sb in size_blocks:
            size = sb.get("data-attr-value") or sb.get("prodsize") or sb.get("aria-label")
            size = size.strip().replace(",", ".") if size else "Unknown"
            available = "1" if "disabled" not in sb.get("class", []) else "0"
            size_stock[size] = available

        size_str = ";".join(
            f"{size}:{'有货' if flag == '1' else '无货'}"
            for size, flag in size_stock.items()
        )

        gender = "男款" if "man" in url else "女款" if "woman" in url else "童款"

        info = {
            "Product Code": code,
            "Product Name": name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": full_price,
            "Adjusted Price": discount_price,
            "Product Material": material_text,
            "Product Size": size_str,
            "Source URL": url
        }

        txt_path = TXT_OUTPUT_DIR / f"{code}.txt"
        format_txt(info, txt_path)
        print(f"✅ 写入成功: {code}.txt")

    except Exception as e:
        print(f"❌ 处理失败 {url} → {e}")
    finally:
        driver.quit()

def main():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return

    with open(PRODUCT_LINK_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"🔗 共发现商品链接: {len(urls)}")

    driver = create_driver()
    driver.get(urls[0])
    print("⏳ 请在新窗口手动登录 GEOX（等待 20 秒）")
    time.sleep(20)
    driver.quit()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_url = {executor.submit(process_product, url): url for url in urls}
        for i, future in enumerate(as_completed(future_to_url), 1):
            url = future_to_url[future]
            try:
                future.result()
            except Exception as e:
                print(f"[{i}] ❌ 异常: {url} → {e}")

    print("\n✅ 所有商品处理完成。")

if __name__ == "__main__":
    main()
