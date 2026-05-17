from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
from config import ECCO, ensure_all_dirs, GLOBAL_CHROMEDRIVER_PATH
from selenium.webdriver.chrome.service import Service
import time
import sys

sys.stdout.reconfigure(encoding="utf-8")

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

BASE_URL = "https://gb.ecco.com"
OUTPUT_FILE = ECCO["BASE"] / "publication" / "product_links.txt"


def try_accept_cookies(driver, timeout: int = 8):
    """
    自动点击 'Accept Cookies' / 'Accept All' 按钮（如果有的话）。
    """
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(., 'Accept Cookies') or "
                    "contains(., 'Accept All') or "
                    "contains(., 'ACCEPT ALL')]",
                )
            )
        )
        btn.click()
        time.sleep(0.5)
        print("✅ 已自动点击 Cookies 弹窗")
    except Exception:
        # 没弹窗就算了
        pass


def click_show_more_until_end(driver, timeout: int = 10, max_rounds: int = 200):
    """
    反复点击“Show More”直到按钮消失或达到上限。
    ECCO 新版列表页：
    - 按钮：data-testid="pagination-results-button"
    """
    rounds = 0
    while rounds < max_rounds:
        try:
            btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, '[data-testid="pagination-results-button"]')
                )
            )
            # 滚动到按钮附近，避免不可见
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.2)
            btn.click()
            rounds += 1
            print(f"   🔁 第 {rounds} 次点击 Show More")

            # 等商品网格有新内容渲染（粗略等一下）
            WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, '[data-testid="product-list-grid"]')
                )
            )
            time.sleep(0.5)
        except Exception:
            print("   ⛳ 未找到更多 Show More 按钮，认为已到底")
            break


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
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="product-list-grid"]')
            )
        )
    except Exception:
        print("⚠️ 列表网格等待超时，继续尝试抓取链接")

    # 自动点“Show More”直到全部加载
    click_show_more_until_end(driver, timeout=10)

    links = set()

    # 方式一：从商品卡片里拿链接
    anchors = driver.find_elements(
        By.CSS_SELECTOR,
        '[data-testid="ProductTile"] a.chakra-link[href*="/product/"]',
    )
    for a in anchors:
        href = a.get_attribute("href")
        if href and "/product/" in href:
            links.add(href)

    # 方式二（兜底）：整个网格里抓所有 /product/ 链接
    if not links:
        fallback = driver.find_elements(
            By.CSS_SELECTOR,
            '[data-testid="product-list-grid"] a[href*="/product/"]',
        )
        for a in fallback:
            href = a.get_attribute("href")
            if href and "/product/" in href:
                links.add(href)

    return links


def ecco_get_links():
    ensure_all_dirs(OUTPUT_FILE.parent)

    options = Options()
    # 如需后台运行，可打开下面这一行：
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service(GLOBAL_CHROMEDRIVER_PATH), options=options)

    try:
        all_links = set()
        is_first_page = True

        for url, label in TARGET_URLS:
            print(f"\n🔍 正在打开 [{label}]: {url}")
            driver.get(url)
            time.sleep(5)

            # 只在第一次打开时尝试点 Cookies，后面一般不会再出现
            if is_first_page:
                try_accept_cookies(driver)
                is_first_page = False

            # 确保主商品区域加载完成
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-testid="product-list-grid"]')
                    )
                )
            except Exception:
                print("⚠️ 主商品区域等待超时，仍尝试抓取")

            # 自动“翻页”+提取链接
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
