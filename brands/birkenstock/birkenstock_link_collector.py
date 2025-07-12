from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from pathlib import Path
from config import BIRKENSTOCK, ensure_all_dirs
import time

BASE_URLS = [
    ("https://www.birkenstock.com/gb/women/sandals/", "Women Sandals"),
    ("https://www.birkenstock.com/gb/women/shoes/", "Women Shoes"),
    ("https://www.birkenstock.com/gb/women/slippers/", "Women slipper"),
    ("https://www.birkenstock.com/gb/men/sandals/", "Men Sandals"),
    ("https://www.birkenstock.com/gb/men/shoes/", "Men Shoes"),
    ("https://www.birkenstock.com/gb/men/slippers/", "Men slippers")
]
OUTPUT_FILE = BIRKENSTOCK["BASE"] / "publication" / "product_links.txt"

def collect_links_from_page(driver):
    links = set()
    elements = driver.find_elements(By.CSS_SELECTOR, "a.color-swatch.mobile-selectable")
    for elem in elements:
        href = elem.get_attribute("href")
        if href and href.startswith("http"):
            links.add(href.strip())
    return links

def main():
    ensure_all_dirs(OUTPUT_FILE.parent)

    options = Options()
    # options.add_argument("--headless")  # 显示浏览器窗口，方便手动加载
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        all_links = set()

        for url, label in BASE_URLS:
            print(f"\n🔍 正在打开 [{label}]: {url}")
            driver.get(url)
            time.sleep(5)

            print("🟡 请手动点击 Accept Cookies，并手动点击页面中的所有 Show More 或下拉滚动至底部，确保加载完整商品")
            input(f"⏸️ 加载 [{label}] 页面完成后，请按回车继续提取链接 >>> ")

            links = collect_links_from_page(driver)
            all_links.update(links)
            print(f"✅ [{label}] 页面提取到 {len(links)} 条链接")

        # 保存所有链接
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for link in sorted(all_links):
                f.write(link + "\n")

        print(f"\n🎉 共提取商品链接 {len(all_links)} 条")
        print(f"📄 已保存至: {OUTPUT_FILE}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
