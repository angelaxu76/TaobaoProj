# barbour/supplier/houseoffraser_get_links.py

import time
from pathlib import Path
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import BARBOUR

# 配置分页地址和输出路径
BASE_URL = "https://www.houseoffraser.co.uk/brand/barbour/coats-and-jackets"
PAGE_URL_TEMPLATE = BASE_URL + "#dcp={}&dppp=59&OrderBy=rank"
OUTPUT_PATH = BARBOUR["LINKS_FILES"]["houseoffraser"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_driver():
    options = uc.ChromeOptions()
    # 👉 如需静默运行可启用 headless
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, use_subprocess=True)
    return driver


def extract_links_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.select("a.ProductImageList"):
        href = tag.get("href", "").strip()
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.houseoffraser.co.uk" + href)
    return links


def houseoffraser_get_links():
    print("🚀 开始抓取 House of Fraser 商品链接")
    driver = get_driver()
    all_links = set()
    page = 1

    while True:
        page_url = PAGE_URL_TEMPLATE.format(page)
        print(f"🌐 抓取第 {page} 页: {page_url}")
        driver.get(page_url)

        try:
            # 显式等待商品元素加载
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ProductImageList"))
            )
        except Exception as e:
            print(f"⚠️ 第 {page} 页等待超时或无商品，终止抓取")
            break

        html = driver.page_source
        links = extract_links_from_html(html)
        if not links:
            print(f"⚠️ 第 {page} 页未提取到链接，终止")
            break

        print(f"✅ 第 {page} 页提取 {len(links)} 个商品链接")
        all_links.update(links)
        page += 1

    driver.quit()

    # 写入去重后链接到文件
    OUTPUT_PATH.write_text("\n".join(sorted(all_links)), encoding="utf-8")
    print(f"\n🎯 共提取 {len(all_links)} 条商品链接，已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    houseoffraser_get_links()
