# barbour/supplier/allweathers_get_links.py

import time
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
from config import BARBOUR

# === 页面与输出配置 ===
BASE_URL = "https://www.allweathers.co.uk/collections/barbour"
PAGE_TEMPLATE = BASE_URL + "?page={}"
OUTPUT_PATH = BARBOUR["LINKS_FILES"]["allweathers"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")  # ✅ 启用新版无头模式
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)

def extract_links_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.select("a.product-title.h6"):
        href = tag.get("href", "").strip()
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.allweathers.co.uk" + href)
    return links

def allweathers_get_links():
    print("🚀 开始抓取 Allweathers 商品链接")
    driver = get_driver()
    all_links = set()
    page = 1

    while True:
        url = PAGE_TEMPLATE.format(page)
        print(f"🌐 抓取第 {page} 页: {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-title.h6"))
            )
        except:
            print(f"⚠️ 第 {page} 页加载超时或无商品，终止")
            break

        html = driver.page_source
        links = extract_links_from_html(html)

        if not links:
            print(f"⚠️ 第 {page} 页未提取到链接，终止")
            break

        print(f"✅ 第 {page} 页提取 {len(links)} 个商品链接")
        all_links.update(links)
        page += 1
        time.sleep(1)

    driver.quit()

    # 写入文件
    OUTPUT_PATH.write_text("\n".join(sorted(all_links)), encoding="utf-8")
    print(f"\n🎯 共提取 {len(all_links)} 条商品链接，已保存至：{OUTPUT_PATH}")

if __name__ == "__main__":
    allweathers_get_links()
