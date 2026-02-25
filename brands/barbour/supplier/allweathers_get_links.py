import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import BARBOUR
from common.browser.selenium_utils import get_driver, quit_driver

# ========= 类目配置：在这里增删类目链接 =========
CATEGORY_URLS = [
    "https://www.allweathers.co.uk/collections/barbour",
    "https://www.allweathers.co.uk/collections/barbour-quilted-jackets-1",
    "https://www.allweathers.co.uk/collections/barbour-coats-long",
    "https://www.allweathers.co.uk/collections/barbour-waxed-jackets",
    "https://www.allweathers.co.uk/collections/barbour-waterproof-jackets",
    "https://www.allweathers.co.uk/collections/barbour-gilets",
    "https://www.allweathers.co.uk/collections/barbour-liners",
    "https://www.allweathers.co.uk/collections/barbour-fleece-gilets",
    "https://www.allweathers.co.uk/collections/barbour-knitwear",
    "https://www.allweathers.co.uk/collections/barbour-sweatshirts-hoodies",
]

# 输出路径仍然复用原来的配置
OUTPUT_PATH = BARBOUR["LINKS_FILES"]["allweathers"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_allweathers_driver():
    """
    统一从 common.selenium_utils 获取 driver，
    名字用 'allweathers'，方便以后复用或单独关闭。
    """
    return get_driver(
        name="allweathers",
        headless=False,           # 需要可视化就关掉 headless
        window_size="1200,2000",
    )


def extract_links_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.select("a.product-title.h6"):
        href = tag.get("href", "").strip()
        if not href:
            continue
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.allweathers.co.uk" + href)
    return links


def build_page_url(base_url: str, page: int) -> str:
    """根据是否已有 ? 构造分页 URL，避免 ?page= 拼错"""
    if "?" in base_url:
        return f"{base_url}&page={page}"
    else:
        return f"{base_url}?page={page}"


def allweathers_get_links():
    print("🚀 开始抓取 Allweathers 多类目商品链接")
    driver = get_allweathers_driver()
    all_links = set()

    try:
        for idx, base_url in enumerate(CATEGORY_URLS, start=1):
            print("\n============================")
            print(f"📂 类目 {idx}/{len(CATEGORY_URLS)}: {base_url}")
            page = 1

            while True:
                url = build_page_url(base_url, page)
                print(f"🌐 抓取第 {page} 页: {url}")
                driver.get(url)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "a.product-title.h6")
                        )
                    )
                except Exception:
                    print(f"⚠️ 第 {page} 页加载超时或无商品，终止该类目分页")
                    break

                html = driver.page_source
                links = extract_links_from_html(html)

                if not links:
                    print(f"⚠️ 第 {page} 页未提取到链接，终止该类目分页")
                    break

                print(f"✅ 第 {page} 页提取 {len(links)} 个商品链接")
                all_links.update(links)

                page += 1
                time.sleep(1)

    finally:
        # 使用公共工具关闭 'allweathers' 这个 driver
        quit_driver("allweathers")

    # 写入文件（去重后的总集合）
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sorted(all_links)), encoding="utf-8")

    print("\n🎯 抓取完成")
    print(f"📦 共提取 {len(all_links)} 条商品链接（多类目去重后总数）")
    print(f"💾 已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    allweathers_get_links()
