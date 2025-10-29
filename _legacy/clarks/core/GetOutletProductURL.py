
import requests
from bs4 import BeautifulSoup
import re

LINK_PATTERN = r"https://www\.clarksoutlet\.co\.uk/[\w\-]+/\d+-p"

URLS = {
    "women_shoes": "https://www.clarksoutlet.co.uk/womens/womens-shoes/w_shoes_uko-c?page=7",
    "women_new": "https://www.clarksoutlet.co.uk/womens/womens-new-in/w_new_uko-c?page=7",
    "women_sandals": "https://www.clarksoutlet.co.uk/womens/womens-sandals/w_sandals_uko-c?page=3",
    "women_originals": "https://www.clarksoutlet.co.uk/womens-originals/wo_allstyles_uko-c?page=3",
    "women_boots": "https://www.clarksoutlet.co.uk/womens/womens-boots/w_boots_uko-c?page=3",
    "men_shoes": "https://www.clarksoutlet.co.uk/mens/mens-shoes/m_shoes_uko-c?page=5",
    "men_new": "https://www.clarksoutlet.co.uk/mens/mens-new-in/m_new_uko-c?page=7",
    "men_boots": "https://www.clarksoutlet.co.uk/mens/mens-boots/m_boots_uko-c?page=3",
    "men_originals": "https://www.clarksoutlet.co.uk/mens-originals/mo_allstyles_uko-c?page=3"
}

def get_outlet_product_links():
    all_links = set()

    for category, url in URLS.items():
        print(f"📦 正在抓取 OUTLET 分类: {category}")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"  ❌ 请求失败：{e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        hrefs = [a['href'] for a in soup.find_all('a', href=True)]
        matched_links = {href for href in hrefs if re.match(LINK_PATTERN, href)}
        print(f"  ✅ 抓取 {len(matched_links)} 条链接")
        all_links.update(matched_links)

    print(f"✅ 总共抓取 OUTLET 链接 {len(all_links)} 条")
    return sorted(all_links)
