
import requests
from bs4 import BeautifulSoup
import re
import time

BASE_DOMAIN = "https://www.clarksoutlet.co.uk"
# 新版官网链接为相对路径：/en-vg/<product-name>/<id>-p
LINK_PATTERN = re.compile(r"^/en-vg/[\w\-]+/\d+-p$")

URLS = {
    "women_shoes":      f"{BASE_DOMAIN}/womens/womens-shoes/w_shoes_uko-c",
    "women_new":        f"{BASE_DOMAIN}/womens/womens-new-in/w_new_uko-c",
    "women_flats":      f"{BASE_DOMAIN}/womens/womens-flat-shoes/w_flats_uko-c",
    "women_heels":      f"{BASE_DOMAIN}/womens/womens-heels/w_heels_uko-c",
    "women_balletpumps": f"{BASE_DOMAIN}/womens/womens-pumps/w_balletpumps_uko-c",
    "women_loafers":    f"{BASE_DOMAIN}/womens/womens-loafers/w_loafers_uko-c",
    "women_sport":      f"{BASE_DOMAIN}/womens/womens-sport/w_sport_uko-c",
    "women_slippers":   f"{BASE_DOMAIN}/womens/womens-slippers/w_slippers_uko-c",
    "women_sandals":    f"{BASE_DOMAIN}/womens/womens-sandals/w_sandals_uko-c",
    "women_boots":      f"{BASE_DOMAIN}/womens/womens-boots/w_boots_uko-c",
    "women_originals":  f"{BASE_DOMAIN}/womens-originals/wo_allstyles_uko-c",
    "men_shoes":        f"{BASE_DOMAIN}/mens/mens-shoes/m_shoes_uko-c",
    "men_new":          f"{BASE_DOMAIN}/mens/mens-new-in/m_new_uko-c",
    "men_boots":        f"{BASE_DOMAIN}/mens/mens-boots/m_boots_uko-c",
    "men_originals":    f"{BASE_DOMAIN}/mens-originals/mo_allstyles_uko-c",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_outlet_product_links():
    all_links = set()

    for category, url in URLS.items():
        print(f"📦 正在抓取 OUTLET 分类: {category}")
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"  ❌ 请求失败：{e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        matched = {
            BASE_DOMAIN + a["href"]
            for a in soup.find_all("a", href=True)
            if LINK_PATTERN.match(a["href"])
        }
        print(f"  ✅ 抓取 {len(matched)} 条链接")
        all_links.update(matched)
        time.sleep(0.5)

    print(f"✅ 总共抓取 OUTLET 链接 {len(all_links)} 条")
    return sorted(all_links)
