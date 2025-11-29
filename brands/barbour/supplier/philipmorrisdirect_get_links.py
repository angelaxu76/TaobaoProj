# barbour/supplier/philipmorris_get_links.py

import time
from pathlib import Path
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import BARBOUR

# ====== 多个分类 URL，按需增减 ======
CATEGORY_URLS = [
    "https://www.philipmorrisdirect.co.uk/brand/barbour/",
    "https://www.philipmorrisdirect.co.uk/brand/barbour/barbour-menswear/",
    "https://www.philipmorrisdirect.co.uk/brand/barbour/barbour-jackets/",
    "https://www.philipmorrisdirect.co.uk/brand/barbour/barbour-womenswear/",
    "https://www.philipmorrisdirect.co.uk/brand/barbour/barbour-gilets/",
    "https://www.philipmorrisdirect.co.uk/brand/barbour/barbour-jumpers/",
]

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["philipmorris"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)


def extract_links_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.select("a.card-figure__link"):
        href = tag.get("href", "").strip()
        if not href:
            continue
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.philipmorrisdirect.co.uk" + href)
    return links


def philipmorris_get_links():
    print("🚀 开始抓取 Philip Morris 商品链接（多分类）")
    driver = get_driver()
    all_links = set()

    try:
        for base_url in CATEGORY_URLS:
            print(f"\n📂 当前分类: {base_url}")
            page = 1

            while True:
                # 每个分类单独翻页
                page_url = f"{base_url}?page={page}"
                print(f"🌐 抓取第 {page} 页: {page_url}")
                driver.get(page_url)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.card-figure__link"))
                    )
                except Exception:
                    print(f"⚠️ 第 {page} 页加载超时或无商品，结束该分类")
                    break

                html = driver.page_source
                links = extract_links_from_html(html)
                if not links:
                    print(f"⚠️ 第 {page} 页未提取到链接，结束该分类")
                    break

                print(f"✅ 第 {page} 页提取 {len(links)} 个商品链接")
                all_links.update(links)

                page += 1
                time.sleep(1)

    finally:
        driver.quit()

    # 统一去重后写入文件
    sorted_links = sorted(all_links)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sorted_links), encoding="utf-8")
    print(f"\n🎯 共提取 {len(sorted_links)} 条商品链接（多分类去重后），已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    philipmorris_get_links()
