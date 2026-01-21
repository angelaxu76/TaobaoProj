import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import BARBOUR
from pathlib import Path
import time

BASE_URL = "https://www.barbour.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

CATEGORY_URLS = {
    "mens-jackets": "https://www.barbour.com/gb/mens/jackets",
    "womens-jackets": "https://www.barbour.com/gb/womens/jackets",
    "mens-internaltion-jackets": "https://www.barbour.com/gb/barbour-international/mens",
    "womens-internaltion-jackets": "https://www.barbour.com/gb/barbour-international/womens",
    "paul-smith": "https://www.barbour.com/gb/all-collaborations/paul-smith-loves-barbour",
    "margaret": "https://www.barbour.com/gb/all-collaborations/barbour-for-margaret-howell",
    "barbour-farm-rio": "https://www.barbour.com/gb/womens/collaborations/barbour-farm-rio",
    "wsunshine": "https://www.barbour.com/gb/all-collaborations/barbour-x-kaptain-sunshine-",
}

# CATEGORY_URLS = {
#     "paul-smith": "https://www.barbour.com/gb/all-collaborations/paul-smith-loves-barbour",
#     "margaret": "https://www.barbour.com/gb/all-collaborations/barbour-for-margaret-howell",
#     "barbour-farm-rio": "https://www.barbour.com/gb/womens/collaborations/barbour-farm-rio",
#     "wsunshine": "https://www.barbour.com/gb/all-collaborations/barbour-x-kaptain-sunshine-"
# }

OUTPUT_FILE = BARBOUR["LINKS_FILE"]


def get_links_from_page(url):
    print(f"📄 抓取页面: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        urljoin(BASE_URL, a['href'])
        for a in soup.find_all("a", class_="link", href=True)
        if a['href'].endswith(".html")
    ]


def get_all_links_for_category(base_url, max_pages=100):
    all_links = []
    for start in range(0, max_pages * 12, 12):
        page_url = f"{base_url}?start={start}&sz=12" if start > 0 else base_url
        links = get_links_from_page(page_url)
        if not links:
            break
        all_links.extend(links)
        time.sleep(1)
    return all_links


def barbour_get_links():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_links = []
    for name, url in CATEGORY_URLS.items():
        print(f"\n🔍 分类: {name}")
        links = get_all_links_for_category(url)
        all_links.extend(links)

    unique_links = sorted(set(all_links))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for link in unique_links:
            f.write(link.strip() + "\n")

    print(f"\n✅ 共写入 {len(unique_links)} 条链接 → {OUTPUT_FILE}")


if __name__ == "__main__":
    barbour_get_links()
