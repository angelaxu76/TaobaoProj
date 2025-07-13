# TODO: 实现 camper 商品链接抓取逻辑（增强版）
import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path
from config import CAMPER_GLOBAL  # ✅ 根据品牌切换
import sys

sys.stdout.reconfigure(encoding='utf-8')

# ========= 参数配置 =========
LINKS_FILE = CAMPER_GLOBAL["LINKS_FILE"]
TOTAL_PAGES = 15
WAIT = 1
MAX_EMPTY_PAGES = 3
LINK_PREFIX = "https://www.camper.com"

BASE_URLS = [
    # 🇩🇪 德国
    "https://www.camper.com/en_DE/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_DE/men/shoes?sort=default&page={}",
    "https://www.camper.com/en_DE/kids/shoes?sort=default&page={}",
    "https://www.camper.com/en_DE/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_DE/men/shoes/all_shoes_lab_men?filter.collection=allabw&sort=default&page={}",

    # 🇨🇦 加拿大
    "https://www.camper.com/en_CA/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_CA/men/shoes?sort=default&page={}",
    "https://www.camper.com/en_CA/kids/shoes?sort=default&page={}",
    "https://www.camper.com/en_CA/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_CA/men/shoes/all_shoes_lab_men?filter.collection=allabw&sort=default&page={}",

    # 🇦🇺 澳洲（如需添加）
    "https://www.camper.com/en_AU/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_AU/men/shoes?sort=default&page={}",
    "https://www.camper.com/en_AU/kids/shoes?sort=default&page={}",
    "https://www.camper.com/en_AU/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_AU/men/shoes/all_shoes_lab_men?filter.collection=allabw&sort=default&page={}"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}


# ========= 带重试机制的请求函数 =========
def fetch_with_retry(url, retries=3, timeout=20):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"❌ 第 {attempt} 次请求失败: {url}，错误: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return None


# ========= 链接提取函数 =========
def get_links_from_page(url):
    html = fetch_with_retry(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    product_divs = soup.find_all("div", class_="ant-col grid-item overflow-hidden ant-col-xs-12 ant-col-md-8 ant-col-lg-6 ant-col-xl-6 ant-col-xxl-6")

    links = []
    for div in product_divs:
        a_tag = div.find("a", class_="block")
        if a_tag and a_tag.get("href"):
            href = a_tag["href"]
            if href.startswith("/"):
                href = LINK_PREFIX + href
            links.append(href)

    return links


# ========= 主程序 =========
def main():
    all_links = set()

    for base_url in BASE_URLS:
        empty_pages = 0
        for page in range(1, TOTAL_PAGES + 1):
            url = base_url.format(page)
            print(f"\n🌐 抓取: {url}")
            links = get_links_from_page(url)
            if links:
                print(f"✅ 第 {page} 页: {len(links)} 条链接")
                all_links.update(links)
                empty_pages = 0
            else:
                print(f"⚠️ 第 {page} 页无链接或抓取失败")
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    print(f"⏹️ 连续 {MAX_EMPTY_PAGES} 页为空，提前终止该入口抓取")
                    break
            time.sleep(WAIT)

    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共抓取链接: {len(all_links)}，已保存到: {LINKS_FILE}")

if __name__ == "__main__":
    main()
