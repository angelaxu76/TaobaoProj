# barbour/supplier/houseoffraser_get_links.py

import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import BARBOUR

# ✅ 两个入口：Barbour & Barbour International（第1页无参，其余 ?dcp=N）
BASE_URLS = [
    "https://www.houseoffraser.co.uk/brand/barbour",
    "https://www.houseoffraser.co.uk/brand/barbour-international",
]

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["houseoffraser"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# 商品详情链接的通用特征：结尾/片段中带 -123456 这类数字 ID（不少还带 #colcode=）
PRODUCT_HREF_PATTERN = re.compile(r"-\d{5,}([/#?]|$)")


def get_driver():
    options = uc.ChromeOptions()
    # 如需静默运行可启用
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
    driver = uc.Chrome(options=options, use_subprocess=True)
    return driver


def _build_page_url(base_url: str, page: int) -> str:
    """HoF 分页：第1页无参，其余页使用 ?dcp=N"""
    if page <= 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}dcp={page}"


def _wait_products(driver):
    """等待商品元素出现"""
    wait_css = ", ".join([
        "a.ProductImageList",
        "a[data-testid*='product']",
        "a[href*='-'][href*='/']",
    ])
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
        )
        return True
    except Exception:
        return False


def extract_links_from_html(html: str):
    """提取商品链接"""
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    for tag in soup.select("a.ProductImageList"):
        href = (tag.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.houseoffraser.co.uk" + href)

    if links:
        return links

    # 兜底：包含 -数字(≥5位) 的链接
    for tag in soup.select("a[href]"):
        href = (tag.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            full = "https://www.houseoffraser.co.uk" + href
        elif href.startswith("http"):
            full = href
        else:
            continue
        if PRODUCT_HREF_PATTERN.search(href):
            links.add(full)

    return links


def _crawl_category(driver, base_url: str, all_links: set, max_pages: int = 60):
    """抓取单个分类"""
    page = 1
    while page <= max_pages:
        page_url = _build_page_url(base_url, page)
        print(f"🌐 抓取第 {page} 页: {page_url}")
        driver.get(page_url)

        if not _wait_products(driver):
            print(f"⚠️ 第 {page} 页未检测到商品元素，结束该分类")
            break

        html = driver.page_source
        links = extract_links_from_html(html)
        new_links = [u for u in links if u not in all_links]

        if not new_links:
            print(f"ℹ️ 第 {page} 页无新增链接，结束该分类")
            break

        print(f"✅ 第 {page} 页提取 {len(new_links)} 个新链接")
        all_links.update(new_links)
        page += 1


def houseoffraser_get_links():
    print("🚀 开始抓取 House of Fraser 商品链接（Barbour & Barbour International）")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = get_driver()

    # ✅ 只在首次加载第一个分类前停留 10 秒手动点击 Cookie
    print("🕒 已打开浏览器，请在 10 秒内手动点击 Cookie 的 'Allow all' 按钮 ...")
    driver.get(BASE_URLS[0])
    time.sleep(10)
    print("✅ 已等待 10 秒，开始正式抓取")

    all_links = set()

    # ✅ 复用同一个 browser instance 抓取两个分类
    for base in BASE_URLS:
        print(f"\n===== 🧭 当前分类：{base} =====")
        _crawl_category(driver, base, all_links)

    driver.quit()

    # 写入 TXT
    OUTPUT_PATH.write_text("\n".join(sorted(all_links)), encoding="utf-8")
    print(f"\n🎯 共提取 {len(all_links)} 条商品链接，已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    houseoffraser_get_links()
