import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import ECCO, ensure_all_dirs

# 解决 Windows 控制台中文输出问题
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# === 需要抓取的类目页面 ===
TARGET_URLS = [
    ("https://gb.ecco.com/women/shoes", "Women"),
    ("https://gb.ecco.com/men/shoes", "Men"),
    ("https://gb.ecco.com/outdoor/women", "Women Outdoor"),
    ("https://gb.ecco.com/outdoor/men", "Men Outdoor"),
    ("https://gb.ecco.com/golf", "Golf"),
    ("https://gb.ecco.com/kids/junior", "Kids Junior"),
    ("https://gb.ecco.com/kids/boys/shoes", "Kids Boys Shoes"),
    ("https://gb.ecco.com/kids/girls/shoes", "Kids Girls Shoes"),
    ("https://gb.ecco.com/sale/women", "women sale"),
    ("https://gb.ecco.com/sale/men", "men sale"),
    ("https://gb.ecco.com/sale/kids", "kid sale"),
]

OUTPUT_FILE: Path = ECCO["BASE"] / "publication" / "product_links.txt"


# ================== 通用小工具 ==================


def build_driver() -> webdriver.Chrome:
    """
    创建统一配置的 Chrome driver：
    - 禁用通知弹窗（不会再出现 Allow / Block）
    - 最大化窗口
    """
    options = Options()
    # 如需无头模式可以打开下一行：
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")

    # ⭐ 禁用通知弹窗 = 自动等于 Block，Selenium 点不到系统弹窗，所以从根源关闭
    prefs = {
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    return driver


def try_accept_cookies(driver: webdriver.Chrome, timeout: int = 12) -> bool:
    """
    自动处理 ECCO 网站的 Cookie 弹窗：
    - 优先点击 “Accept all cookies”
    - 兼容其他 Accept / Allow / OK 文案
    - 同时尝试主页面和 iframe 内的按钮
    """
    # 常见 cookie 按钮 XPATH 列表（从最精确到最模糊）
    button_xpaths = [
        "//button[normalize-space()='Accept all cookies']",
        "//button[contains(., 'Accept all cookies')]",
        "//button[contains(., 'Accept All Cookies')]",
        "//button[contains(., 'Accept all')]",
        "//button[contains(., 'Accept All')]",
        "//button[contains(., 'ACCEPT ALL')]",
        "//button[contains(., 'Accept')]",
        "//button[contains(., 'ALLOW')]",
        "//button[contains(., 'Allow')]",
        "//button[contains(., 'I Agree')]",
        "//button[contains(., 'OK')]",
        "//button[contains(@id, 'accept')]",
        "//button[contains(@class, 'accept')]",
    ]

    # ---------- 先在主页面找 ----------
    for xp in button_xpaths:
        try:
            btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.2)
            btn.click()
            print("🍪 已自动点击 Cookie 按钮（主页面）")
            return True
        except Exception:
            # 没找到该 xpath 就继续尝试下一个
            continue

    # ---------- 再尝试 iframe 内部 ----------
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        iframes = []

    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
            for xp in button_xpaths:
                try:
                    btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xp))
                    )
                    btn.click()
                    print("🍪 已自动点击 Cookie 按钮（iframe 内）")
                    driver.switch_to.default_content()
                    return True
                except Exception:
                    continue
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
            continue

    print("ℹ️ 未发现 Cookie 弹窗或无需处理")
    return False


def click_show_more_until_end(
    driver: webdriver.Chrome,
    timeout: int = 10,
    max_rounds: int = 200,
):
    """
    反复点击 “Show more” 按钮直到按钮消失或达到上限。
    ECCO 列表页按钮特征：
      data-testid="pagination-results-button"
    """
    rounds = 0
    while rounds < max_rounds:
        try:
            btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, '[data-testid="pagination-results-button"]')
                )
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.2)
            btn.click()
            rounds += 1
            print(f"   🔁 第 {rounds} 次点击 Show more")
            # 等待新商品加载（简单等一下）
            time.sleep(1.0)
        except Exception:
            print("   ⛳ 未找到更多 Show more 按钮，认为已到底")
            break


def collect_links_from_page(driver: webdriver.Chrome) -> set[str]:
    """
    从当前列表页提取所有商品链接，适配 ECCO GB 新版结构：
    - 列表容器：data-testid="product-list-grid"
    - 商品卡片：data-testid="ProductTile"
    - 链接：a.chakra-link[href*='/product/']
    """
    # 等待列表区域出现
    try:
        WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="product-list-grid"]')
            )
        )
    except Exception:
        print("⚠️ 列表网格等待超时，仍尝试继续")

    # 自动点 “Show more” 把所有商品加载出来
    click_show_more_until_end(driver, timeout=10)

    links: set[str] = set()

    # 优先：从 ProductTile 中找
    anchors = driver.find_elements(
        By.CSS_SELECTOR,
        '[data-testid="ProductTile"] a.chakra-link[href*="/product/"]',
    )
    for a in anchors:
        href = a.get_attribute("href")
        if href and "/product/" in href:
            links.add(href)

    # 兜底：整个商品网格里任意 /product/ 链接
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


# ================== 主流程 ==================


def ecco_get_links():
    ensure_all_dirs(OUTPUT_FILE.parent)

    driver = build_driver()

    try:
        all_links: set[str] = set()
        is_first_page = True

        for url, label in TARGET_URLS:
            print(f"\n🔍 正在打开 [{label}]: {url}")
            driver.get(url)
            time.sleep(5)

            # 只在第一次访问时处理 Cookie
            if is_first_page:
                try_accept_cookies(driver)
                is_first_page = False

            # 尝试等待商品列表出现
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-testid="product-list-grid"]')
                    )
                )
            except Exception:
                print("⚠️ 主商品区域等待超时，继续尝试抓取链接")

            # 抓取当前类目所有商品链接
            links = collect_links_from_page(driver)
            all_links.update(links)
            print(f"✅ [{label}] 提取到 {len(links)} 条链接")

        # 写入 TXT
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for link in sorted(all_links):
                f.write(link + "\n")

        print("\n🎉 所有类目抓取完成")
        print(f"📦 共采集到产品链接 {len(all_links)} 条")
        print(f"📄 已保存到: {OUTPUT_FILE}")

    finally:
        driver.quit()


if __name__ == "__main__":
    ecco_get_links()
