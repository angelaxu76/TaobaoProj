from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from pathlib import Path
from config import ECCO, ensure_all_dirs
import time



# === 页面配置 ===
TARGET_URLS = [
    ("https://gb.ecco.com/en-GB/Women/Shoes", "Women"),
    ("https://gb.ecco.com/en-GB/Men/Shoes", "Men"),
    ("https://gb.ecco.com/en-GB/Outdoor/Women", "Women Outdoor"),
    ("https://gb.ecco.com/en-GB/Outdoor/Men", "Men Outdoor"),
    ("https://gb.ecco.com/en-GB/Golf", "Golf")
]
BASE_URL = "https://gb.ecco.com"
OUTPUT_FILE = ECCO["BASE"] / "publication" / "product_links.txt"

def collect_links_from_page(driver):
    elements = driver.find_elements(By.CLASS_NAME, "product-item__link")
    links = set()
    for elem in elements:
        href = elem.get_attribute("href") or elem.get_attribute("ng-href")
        if href and "/product/" in href:
            if not href.startswith("http"):
                href = BASE_URL + href
            links.add(href)
    return links

def main():
    ensure_all_dirs(OUTPUT_FILE.parent)

    options = Options()
    # options.add_argument("--headless")  # 显示窗口，方便人工操作
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    try:
        all_links = set()

        for url, label in TARGET_URLS:
            print(f"\n🔍 正在打开 [{label}]: {url}")
            driver.get(url)
            time.sleep(5)

            print("🟡 请在浏览器中手动点击 [Accept Cookies] 和不断点击 [Show More] 直到加载完成")
            input(f"⏸️ 加载 [{label}] 页面完成后，请按回车继续提取链接 >>> ")

            links = collect_links_from_page(driver)
            all_links.update(links)
            print(f"✅ [{label}] 页面提取到 {len(links)} 条链接")

        # 保存全部链接
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for link in sorted(all_links):
                f.write(link + "\n")

        print(f"\n🎉 所有页面共采集产品链接 {len(all_links)} 条")
        print(f"📄 已保存至: {OUTPUT_FILE}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
