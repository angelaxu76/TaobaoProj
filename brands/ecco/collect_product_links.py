from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from pathlib import Path
from config import ECCO, ensure_all_dirs
import time

import sys
sys.stdout.reconfigure(encoding='utf-8')

# === 页面配置 ===
TARGET_URLS = [
    ("https://gb.ecco.com/women/shoes", "Women"),
    ("https://gb.ecco.com/men/shoes", "Men"),
    ("https://gb.ecco.com/outdoor/women", "Women Outdoor"),
    ("https://gb.ecco.com/outdoor/men", "Men Outdoor"),
    ("https://gb.ecco.com/golf", "Golf"),
    ("https://gb.ecco.com/kids/junior", "Kids Junior"),
    ("https://gb.ecco.com/kids/boys/shoes", "Kids Boys Shoes"),
    ("https://gb.ecco.com/kids/girls/shoes", "Kids Girls Shoes"),
]

MANUAL_MODE = True 
BASE_URL = "https://gb.ecco.com"
OUTPUT_FILE = ECCO["BASE"] / "publication" / "product_links.txt"

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def wait_for_user_ready(label: str):
    print(f"⏸️ [{label}]：请在浏览器中手动“Accept Cookies”，并反复点击“Show More”直到按钮消失、页面到底。")
    input("👉 都完成后，按回车键开始提取该页链接…")
def click_show_more_until_end(driver, timeout=10, max_rounds=200):
    """
    反复点击“Show More”直到按钮消失或达到上限。
    """
    rounds = 0
    while rounds < max_rounds:
        try:
            # 按钮出现就点
            btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="pagination-results-button"]'))
            )
            btn.click()
            rounds += 1
            # 每次点击后等商品网格有新内容渲染
            WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-testid="product-list-grid"]'))
            )
            time.sleep(0.5)
        except Exception:
            break  # 没有按钮或不可点击 => 已经到底

def collect_links_from_page(driver):
    """
    适配新版 ECCO 列表页结构：
    - 列表容器：data-testid="product-list-grid"
    - 商品卡片：data-testid="ProductTile"
    - 链接：a.chakra-link[href*="/product/"]
    """
    # 等列表网格渲染
    try:
        WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-testid="product-list-grid"]'))
        )
    except Exception:
        pass

    # 自动点“Show More”直到全部加载
    click_show_more_until_end(driver, timeout=10)

    links = set()
    # 方式一：从商品卡片里拿链接
    anchors = driver.find_elements(By.CSS_SELECTOR, '[data-testid="ProductTile"] a.chakra-link[href*="/product/"]')
    for a in anchors:
        href = a.get_attribute("href")
        if href and "/product/" in href:
            links.add(href)

    # 方式二（兜底）：整个网格里抓所有 /product/ 链接，防止局部类名变动
    if not links:
        fallback = driver.find_elements(By.CSS_SELECTOR, '[data-testid="product-list-grid"] a[href*="/product/"]')
        for a in fallback:
            href = a.get_attribute("href")
            if href and "/product/" in href:
                links.add(href)

    return links

def try_accept_cookies(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept Cookies') or contains(., 'Accept All')]"))
        )
        btn.click()
        time.sleep(0.5)
    except Exception:
        pass


def ecco_get_links():
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
    ecco_get_links()
