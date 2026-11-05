import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')


# === 配置项 ===
BASE_URL = "https://www.geox.com"
CATEGORY_URLS = {
    "woman": "https://www.geox.com/en-GB/woman/shoes/",
    "man": "https://www.geox.com/en-GB/man/shoes/",
    "girl": "https://www.geox.com/en-GB/girl/shoes/",
    "boy": "https://www.geox.com/en-GB/boy/shoes/",
    "preteen_girl": "https://www.geox.com/en-GB/kids/preteen_girl/",
    "outlet": "https://www.geox.com/en-GB/outlet/",
}
SAVE_FILE = Path("D:/TB/Products/GEOX/publication/product_links.txt")
HTML_DEBUG_FILE = Path("D:/TB/Products/GEOX/publication/debug_geox_page.html")
MAX_PAGES = 30
PAGE_SIZE = 24

SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)

# 判断是否是商品链接
def is_valid_product_link(href: str) -> bool:
    return (
        href.startswith("https://www.geox.com/en-GB/")
        and href.endswith(".html")
        and re.search(r"[A-Z0-9]{4}\.html$", href) is not None
    )

# 判断是否是服装链接：鞋类编码以 D/U/J/B 开头，服装以 W/M 开头
def is_clothing_link(href: str) -> bool:
    return href.rsplit("-", 1)[-1][0] in "WM"

# 抓取单个类目的所有链接
def fetch_product_links_for_category(category_name: str, category_url: str):
    all_links = set()
    last_soup = None
    print(f"\n🔍 开始抓取类目: {category_name}")

    for page in range(MAX_PAGES):
        page_url = category_url if page == 0 else f"{category_url}?start=0&sz={PAGE_SIZE*(page+1)}"
        print(f"  🔄 第 {page+1} 页: {page_url}")
        response = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            print(f"  ❌ 页面请求失败: {response.status_code}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        last_soup = soup
        candidate_links = soup.find_all("a", href=True)
        count_before = len(all_links)

        for tag in candidate_links:
            full_url = urljoin(BASE_URL, tag["href"])
            if is_valid_product_link(full_url):
                all_links.add(full_url)

        added = len(all_links) - count_before
        print(f"  ✅ 新增链接: {added}")

        if added == 0:
            break

        time.sleep(1)

    return all_links, last_soup

# 主函数
def collect_all_product_links():
    total_links = set()
    last_soup = None

    for category_name, category_url in CATEGORY_URLS.items():
        links, soup = fetch_product_links_for_category(category_name, category_url)
        # outlet 没有鞋类子路径（/outlet/woman/shoes/ 为 404），只能按编码剔除服装
        if category_name == "outlet":
            shoe_links = {link for link in links if not is_clothing_link(link)}
            print(f"  🧥 outlet 剔除服装链接: {len(links) - len(shoe_links)}")
            links = shoe_links
        total_links.update(links)
        last_soup = soup  # 用于保存最后一个页面的 HTML 调试信息

    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        for link in sorted(total_links):
            f.write(link + "\n")
    print(f"\n📦 共提取商品链接: {len(total_links)} 条")
    print(f"📄 链接已保存至: {SAVE_FILE}")

    if last_soup:
        with open(HTML_DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write(last_soup.prettify())
        print(f"📄 最后页面 HTML 已保存至: {HTML_DEBUG_FILE}")

if __name__ == "__main__":
    collect_all_product_links()
