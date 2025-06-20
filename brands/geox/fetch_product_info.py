import time
from bs4 import BeautifulSoup
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from config import GEOX, ensure_all_dirs
from common_taobao.txt_writer import format_txt
import re

PRODUCT_LINK_FILE = GEOX["LINKS_FILE"]
TEXT_OUTPUT_DIR = GEOX["TXT_DIR"]
CHROMEDRIVER_PATH = GEOX["CHROMEDRIVER_PATH"]
TEXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

first_visit = True

def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

def get_html(driver, url):
    global first_visit
    driver.get(url)
    if first_visit:
        print("⏳ 请在浏览器中登录 GEOX（等待 20 秒）")
        time.sleep(20)
        first_visit = False
    else:
        time.sleep(2)
    return driver.page_source

def extract_product_info(url, driver):
    html = get_html(driver, url)
    soup = BeautifulSoup(html, "html.parser")

    code_tag = soup.select_one("span.product-id")
    if not code_tag:
        print(f"⚠️ 页面中未找到商品编码，跳过：{url}")
        return
    code = code_tag.text.strip()

    name_tag = soup.select_one("div.sticky-image img")
    name = name_tag["alt"].strip() if name_tag else "N/A"

    price_tag = soup.select_one("span.product-price span.value")
    full_price = price_tag["content"].strip() if price_tag else ""

    discount_tag = soup.select_one("span.sales.discount span.value")
    discount_price = discount_tag["content"].strip() if discount_tag else full_price

    color_block = soup.select_one("div.sticky-color")
    color = color_block.get_text(strip=True).replace("Color:", "") if color_block else ""

    materials_block = soup.select_one("div.materials-container")
    upper_material = materials_block.get_text(" ", strip=True) if materials_block else ""

    desc_block = soup.select_one("div.product-description div.value")
    description = desc_block.get_text(strip=True) if desc_block else ""

    size_blocks = soup.select("div.size-value")
    sizes = []
    for sb in size_blocks:
        size = sb.get("data-attr-value") or sb.get("prodsize") or sb.get("aria-label")
        size = size.strip().replace(",", ".") if size else "Unknown"
        available = "有货" if "disabled" not in sb.get("class", []) else "无货"
        sizes.append(f"{size}: {available}")

    gender = "男款" if "man" in url else "女款" if "woman" in url else "童款"

    txt_path = TEXT_OUTPUT_DIR / f"{code}.txt"
    info = {
        "product_code": code,
        "product_name": name,
        "original_price": full_price,
        "discount_price": discount_price,
        "color": color,
        "gender": gender,
        "product_url": url,
        "upper_material": upper_material,
        "product_description": description,
        "size_stock": sizes
    }

    format_txt(info, txt_path)
    print(f"📄 信息写入: {txt_path.name}")

def main():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return
    urls = [line.strip() for line in PRODUCT_LINK_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"🔍 发现商品链接: {len(urls)} 条")

    driver = create_driver()
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] 处理: {url}")
        try:
            extract_product_info(url, driver)
        except Exception as e:
            print(f"❌ 错误: {url} → {e}")
    driver.quit()
    print("\n✅ 所有商品信息处理完成。")

if __name__ == "__main__":
    main()