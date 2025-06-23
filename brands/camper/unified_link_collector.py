# TODO: 实现 camper 商品链接抓取逻辑
import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path
from config import CAMPER  # ✅ 根据品牌切换

# ========= 参数配置 =========
LINKS_FILE = CAMPER["LINKS_FILE"]
TOTAL_PAGES = 15
WAIT = 1
LINK_PREFIX = "https://www.camper.com"

# ✅ 多个入口可添加到这里
BASE_URLS = [
    "https://www.camper.com/en_GB/women/shoes?sort=default&page={}",  # 女士运动鞋
    "https://www.camper.com/en_GB/men/shoes?sort=default&page={}",   # 男士运动鞋
    "https://www.camper.com/en_GB/kids/shoes?sort=default&page={}",  # 儿童鞋（示例）
    "https://www.camper.com/en_GB/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}", # LAB女鞋（示例）
    "https://www.camper.com/en_GB/men/shoes/all_shoes_lab_men?filter.collection=allabw&sort=default&page={}"# LAB男鞋（示例）
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# ========= 链接提取函数 =========
def get_links_from_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {url}，错误: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
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
        for page in range(1, TOTAL_PAGES + 1):
            url = base_url.format(page)
            print(f"🌐 抓取: {url}")
            links = get_links_from_page(url)
            print(f"✅ 第 {page} 页: {len(links)} 条链接")
            all_links.update(links)
            time.sleep(WAIT)

    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共抓取链接: {len(all_links)}，已保存到: {LINKS_FILE}")

if __name__ == "__main__":
    main()
