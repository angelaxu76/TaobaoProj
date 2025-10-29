
import requests
from bs4 import BeautifulSoup
import time

TOTAL_PAGES = 3
DELAY_PER_REQUEST = 1
LINK_PREFIX = "https://www.clarks.com"
TARGET_LINK_CLASS = "gGNOkU"

BASE_URL_TEMPLATES = {
    "women_shoes": "https://www.clarks.com/en-gb/womens/womens-shoes/w_shoes_uk-c?page={}",
    "women_new": "https://www.clarks.com/en-gb/womens/womens-new-in-shoes/w_new_uk-c?page={}",
    "womens_sandals": "https://www.clarks.com/en-gb/womens/womens-sandals/w_sandals_uk-c?page={}",
    "womens_boots": "https://www.clarks.com/en-gb/womens-boots/w_boots_uk-c?page={}",
    "womens_originals": "https://www.clarks.com/en-gb/womens-originals/wo_allstyles_uk-c?page={}",
    "mens_shoes": "https://www.clarks.com/en-gb/mens/mens-shoes/m_shoes_uk-c?page={}",
    "mens_new": "https://www.clarks.com/en-gb/mens/mens-new-in-shoes/m_new_uk-c?page={}",
    "mens_boots": "https://www.clarks.com/en-gb/mens-boots/m_boots_uk-c?page={}",
    "mens_originals": "https://www.clarks.com/en-gb/mens-originals/mo_allstyles_uk-c?page={}"
}

def get_links_from_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {url}，错误: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    product_links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("https://www.clarks.com/en-gb/") and href.endswith("-p"):
            product_links.append(href)
        elif href.startswith("/en-gb/") and href.endswith("-p"):
            product_links.append(LINK_PREFIX + href)

    return product_links


def get_regular_product_links():
    all_links = set()

    for category, template in BASE_URL_TEMPLATES.items():
        print(f"📦 正在抓取分类: {category}")
        for page in range(1, TOTAL_PAGES + 1):
            url = template.format(page)
            links = get_links_from_page(url)
            print(f"  🔹 第 {page} 页: 获取 {len(links)} 条链接")
            all_links.update(links)
            time.sleep(DELAY_PER_REQUEST)

    print(f"✅ 总共抓取普通商品链接 {len(all_links)} 条")
    return sorted(all_links)
