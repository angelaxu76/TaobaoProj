import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import BARBOUR

BASE_URL = "https://www.barbour.com"
# 2025 年官网改版后，分类页本身的 ?start=&sz= 参数已失效（永远只返回首屏商品）。
# 真正的翻页走这个 AJAX 接口（"Show more" 按钮的 data-ajax-url），
# 需要携带分类页建立的 session cookie，并加上 X-Requested-With 头，否则返回 500。
GRID_URL = f"{BASE_URL}/on/demandware.store/Sites-barbour-gb-Site/en_GB/Search-UpdateGrid"
PAGE_SIZE = 36  # 官网当前每页/每次 Show more 加载的数量

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

CGID_RE = re.compile(r'cgid=([^&"]+)&amp;srule=')
TOTAL_RE = re.compile(r'Showing\s+[\d,]+\s+of\s+([\d,]+)\s+items')

CATEGORY_URLS = {
    # Jackets
    "mens-jackets": "https://www.barbour.com/gb/mens/jackets",
    "womens-jackets": "https://www.barbour.com/gb/womens/jackets",
    "mens-international-jackets": "https://www.barbour.com/gb/barbour-international/mens",
    "womens-international-jackets": "https://www.barbour.com/gb/barbour-international/womens",

    # Collaborations
    # 联名款式经常下架/上新，不要逐个硬编码具体联名子页面（容易漏掉新联名）。
    # 官网有一个汇总所有联名商品的主分类页，覆盖当前在售的全部联名（用它自动跟随官网变化）：
    "all-collaborations": "https://www.barbour.com/gb/all-collaborations",

    # Clothing
    "mens-clothing": "https://www.barbour.com/gb/mens/clothing",
    "mens-Overshirts": "https://www.barbour.com/gb/mens/clothing/overshirts",
    "mens-t-shirts": "https://www.barbour.com/gb/mens/clothing/t-shirts",
    "mens-shirts": "https://www.barbour.com/gb/mens/clothing/shirts",
    "mens-polo-shirts": "https://www.barbour.com/gb/mens/clothing/polo-shirts",
    "womens-clothing": "https://www.barbour.com/gb/womens/clothing",
    "womens-shirts-blouses": "https://www.barbour.com/gb/womens/clothing/shirts-blouses",
    "womens-t-shirts": "https://www.barbour.com/gb/womens/clothing/t-shirts",
    "womens-polo-shirts": "https://www.barbour.com/gb/womens/clothing/polo-shirts",

    # Accessories
    "mens-accessories": "https://www.barbour.com/gb/mens/accessories",
    "womens-accessories": "https://www.barbour.com/gb/womens/accessories",
}

OUTPUT_FILE = BARBOUR["LINKS_FILE"]


def extract_links(html):
    soup = BeautifulSoup(html, "html.parser")
    return [
        urljoin(BASE_URL, a['href'])
        for a in soup.find_all("a", class_="link", href=True)
        if a['href'].endswith(".html")
    ]


def get_all_links_for_category(name, base_url, session, max_pages=200):
    print(f"📄 抓取分类首页: {base_url}")
    try:
        resp = session.get(base_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return []

    html = resp.text
    links = extract_links(html)

    cgid_match = CGID_RE.search(html)
    if not cgid_match:
        # 没有分类网格（专题/联名页可能已下线，或该分类当前无商品）
        return links

    cgid = cgid_match.group(1)
    total_match = TOTAL_RE.search(html)
    total = int(total_match.group(1).replace(",", "")) if total_match else None

    start = PAGE_SIZE
    page = 1
    while page < max_pages:
        if total is not None and start >= total:
            break

        page_url = f"{GRID_URL}?cgid={cgid}&start={start}&sz={PAGE_SIZE}"
        try:
            resp = session.get(
                page_url,
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": base_url},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ 翻页请求失败 ({name}, start={start}): {e}")
            break

        page_links = extract_links(resp.text)
        if not page_links:
            break

        links.extend(page_links)
        start += PAGE_SIZE
        page += 1
        time.sleep(0.5)

    return links


def barbour_get_links():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_links = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for name, url in CATEGORY_URLS.items():
        print(f"\n🔍 分类: {name}")
        links = get_all_links_for_category(name, url, session)
        print(f"   → 共 {len(links)} 条")
        all_links.extend(links)
        time.sleep(1)

    unique_links = sorted(set(all_links))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for link in unique_links:
            f.write(link.strip() + "\n")

    print(f"\n✅ 共写入 {len(unique_links)} 条链接 → {OUTPUT_FILE}")


if __name__ == "__main__":
    barbour_get_links()
