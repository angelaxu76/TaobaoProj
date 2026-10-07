
import requests
from bs4 import BeautifulSoup
import time

from common.browser.selenium_utils import get_driver, quit_driver

MAX_PAGES = 30  # 安全上限；实际会在翻页不再增加新链接时提前停止
DELAY_PER_REQUEST = 1
LINK_PREFIX = "https://www.clarks.com"
TARGET_LINK_CLASS = "gGNOkU"
SELENIUM_HEADLESS = True  # 若 headless 仍被拦，改为 False

# 完整浏览器请求头；只带 "Mozilla/5.0" 会被 Clarks 反爬识别并返回 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_session = requests.Session()
_session.headers.update(HEADERS)
_use_selenium = False  # requests 遇到 403 后切换为 Selenium，本次运行内不再切回

BASE_URL_TEMPLATES = {
    "women_shoes": "https://www.clarks.com/en-gb/womens/womens-shoes/w_shoes_uk-c?page={}",
    "womens_news": "https://www.clarks.com/en-gb/womens/womens-new-in-shoes/w_new_uk-c?page={}",
    "womens_ballet_pumps": "https://www.clarks.com/en-gb/womens/womens-shoes/ballet-pumps/w_balletpumps_uk-c?page={}",
    "womens_black_shoes": "https://www.clarks.com/en-gb/womens/womens-shoes/womens-black-shoes/w_blackshoes_uk-c?page={}",
    "womens_brogues": "https://www.clarks.com/en-gb/womens/womens-shoes/womens-brogues/w_brogues_uk-c?page={}",
    "womens_flats": "https://www.clarks.com/en-gb/womens/womens-shoes/womens-flat-shoes/w_flats_uk-c?page={}",
    "womens_heels": "https://www.clarks.com/en-gb/womens/heels/w_heels_uk-c?page={}",
    "womens_loafers": "https://www.clarks.com/en-gb/womens/womens-shoes/womens-loafers/w_loafers_uk-c?page={}",
    "womens_slippers": "https://www.clarks.com/en-gb/womens/womens-slippers/w_slippers_uk-c?page={}",
    "womens_trainers": "https://www.clarks.com/en-gb/womens/womens-trainers/w_trainers_uk-c?page={}",
    # "womens_sandals": "https://www.clarks.com/en-gb/womens/womens-sandals/w_sandals_uk-c?page={}",
    "womens_black_sandals": "https://www.clarks.com/en-gb/womens/womens-sandals/womens-black-sandals/w_blacksandals_uk-c?page={}",
    "womens_flat_sandals": "https://www.clarks.com/en-gb/womens/womens-sandals/womens-flat-sandals/w_flatsandals_uk-c?page={}",
    "womens_heeled_sandals": "https://www.clarks.com/en-gb/womens/womens-sandals/womens-heeled-sandals/w_heeledsandals_uk-c?page={}",
    "womens_sliders": "https://www.clarks.com/en-gb/womens/womens-sandals/womens-sliders-and-flip-flops/w_sliders_uk-c?page={}",
    "womens_boots": "https://www.clarks.com/en-gb/womens-boots/w_boots_uk-c?page={}",
    "womens_ankle_boots": "https://www.clarks.com/en-gb/womens/womens-boots/womens-ankle-boots/w_ankleboots_uk-c?page={}",
    "womens_chelsea_boots": "https://www.clarks.com/en-gb/womens/womens-boots/womens-chelsea-boots/w_chelseaboots_uk-c?page={}",
    "womens_black_boots": "https://www.clarks.com/en-gb/womens/womens-boots/womens-black-boots/w_blackboots_uk-c?page={}",
    "womens_sale": "https://www.clarks.com/en-gb/womens/womens-sale/w_sale_uk-c?page={}",
    "womens_originals": "https://www.clarks.com/en-gb/womens-originals/wo_allstyles_uk-c?page={}",
    "mens_shoes": "https://www.clarks.com/en-gb/mens/mens-shoes/m_shoes_uk-c?page={}",
    "mens_news": "https://www.clarks.com/en-gb/mens/mens-new-in-shoes/m_new_uk-c?page={}",
    "mens_black_shoes": "https://www.clarks.com/en-gb/mens/mens-shoes/mens-black-shoes/m_blackshoes_uk-c?page={}",
    "mens_boat_shoes": "https://www.clarks.com/en-gb/mens/mens-shoes/mens-boat-shoes/m_boatshoes_uk-c?page={}",
    "mens_loafers": "https://www.clarks.com/en-gb/mens/mens-shoes/mens-loafers/m_loafers_uk-c?page={}",
    "mens_brogues": "https://www.clarks.com/en-gb/mens/mens-shoes/mens-brogues/m_brogues_uk-c?page={}",
    "mens_slippers": "https://www.clarks.com/en-gb/mens/mens-slippers/m_slippers_uk-c?page={}",
    "mens_wide_fit": "https://www.clarks.com/en-gb/mens/mens-wide-fit-shoes/m_wide_uk-c?page={}",
    "mens_trainers": "https://www.clarks.com/en-gb/mens/mens-trainers/m_trainers_uk-c?page={}",
    "mens_boots": "https://www.clarks.com/en-gb/mens-boots/m_boots_uk-c?page={}",
    "mens_waterproof": "https://www.clarks.com/en-gb/mens/mens-waterproof-shoes-and-boots/m_waterproof_uk-c?page={}",
    # "mens_sandals": "https://www.clarks.com/en-gb/mens/mens-sandals/m_sandals_uk-c?page={}",
    "mens_sale": "https://www.clarks.com/en-gb/mens/mens-sale/m_sale_uk-c?page={}",
    "mens_originals": "https://www.clarks.com/en-gb/mens-originals/mo_allstyles_uk-c?page={}",
    "originalsALL": "https://www.clarks.com/en-gb/originals/o_allstyles_uk-c?page={}",
    "cloudsteppers": "https://www.clarks.com/en-gb/cloudsteppers/cloudsteppers_uk-c?page={}",
    "walking": "https://www.clarks.com/en-gb/walking/walking_uk-c?page={}",
    "pace": "https://www.clarks.com/en-gb/pace/pace_walking_shoes_uk-c?page={}",
}

def _fetch_html_requests(url):
    response = _session.get(url, timeout=15)
    response.raise_for_status()
    return response.text


def _fetch_html_selenium(url):
    driver = get_driver("clarks_links", headless=SELENIUM_HEADLESS)
    driver.get(url)
    time.sleep(2)  # 等待前端渲染商品列表
    return driver.page_source


def get_links_from_page(url):
    global _use_selenium
    html = None
    if not _use_selenium:
        try:
            html = _fetch_html_requests(url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                print("⚠️ requests 被拒（403），切换为 Selenium 抓取")
                _use_selenium = True
            else:
                print(f"❌ 请求失败: {url}，错误: {e}")
                return []
        except Exception as e:
            print(f"❌ 请求失败: {url}，错误: {e}")
            return []

    if html is None:
        try:
            html = _fetch_html_selenium(url)
        except Exception as e:
            print(f"❌ Selenium 请求失败: {url}，错误: {e}")
            return []

    soup = BeautifulSoup(html, "html.parser")
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
        for page in range(1, MAX_PAGES + 1):
            url = template.format(page)
            links = get_links_from_page(url)
            if not links:
                break
            before = len(all_links)
            all_links.update(links)
            print(f"  🔹 第 {page} 页: 获取 {len(links)} 条链接（累计 {len(all_links)}）")
            if len(all_links) == before and page > 1:
                # 该分类每页内容是累计返回的（page=N 包含 page<N 的全部商品），
                # 累计数不再增长说明已翻到底
                break
            time.sleep(DELAY_PER_REQUEST)

    quit_driver("clarks_links")
    print(f"✅ 总共抓取普通商品链接 {len(all_links)} 条")
    return sorted(all_links)
