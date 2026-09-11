
import re
import time
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from common.browser.selenium_utils import get_driver, quit_driver

BASE_DOMAIN = "https://www.clarksoutlet.co.uk"
# 商品链接格式：https://www.clarksoutlet.co.uk/<product-name>/<id>-p
LINK_PATTERN_ABS = re.compile(r"^https://www\.clarksoutlet\.co\.uk/[\w\-]+/\d+-p$")
LINK_PATTERN_REL = re.compile(r"^/[\w\-]+/\d+-p$")

URLS = {
    "women_shoes":      f"{BASE_DOMAIN}/womens/womens-shoes/w_shoes_uko-c",
    "women_new":        f"{BASE_DOMAIN}/womens/womens-new-in/w_new_uko-c",
    "women_flats":      f"{BASE_DOMAIN}/womens/womens-flat-shoes/w_flats_uko-c",
    "women_heels":      f"{BASE_DOMAIN}/womens/womens-heels/w_heels_uko-c",
    "women_balletpumps": f"{BASE_DOMAIN}/womens/womens-pumps/w_balletpumps_uko-c",
    "women_loafers":    f"{BASE_DOMAIN}/womens/womens-loafers/w_loafers_uko-c",
    "women_sport":      f"{BASE_DOMAIN}/womens/womens-sport/w_sport_uko-c",
    # "women_slippers":   f"{BASE_DOMAIN}/womens/womens-slippers/w_slippers_uko-c",
    # "women_sandals":    f"{BASE_DOMAIN}/womens/womens-sandals/w_sandals_uko-c",
    "women_flat_sandals":   f"{BASE_DOMAIN}/womens/womens-sandals/womens-flat-sandals/w_flatsandals_uko-c",
    "women_heeled_sandals": f"{BASE_DOMAIN}/womens/womens-sandals/heeled-sandals/w_heeledsandals_uko-c",
    "women_wedge_sandals":  f"{BASE_DOMAIN}/womens/womens-sandals/wedge-sandals/w_wedgesandals_uko-c",
    "women_boots":      f"{BASE_DOMAIN}/womens/womens-boots/w_boots_uko-c",
    "women_black_shoes": f"{BASE_DOMAIN}/womens/womens-black-shoes/w_blackshoes_uko-c",
    "women_wide_fit":   f"{BASE_DOMAIN}/womens/womens-wide-fit/w_widefit_uko-c",
    "women_walking":    f"{BASE_DOMAIN}/walking-styles/walkingstyles_uko-c",
    "women_cloudsteppers": f"{BASE_DOMAIN}/cloudsteppers/cloudsteppers_uko-c",
    "women_sale":       f"{BASE_DOMAIN}/womens/womens-sale/w_sale_uko-c",
    "women_originals":  f"{BASE_DOMAIN}/womens-originals/wo_allstyles_uko-c",
    "men_shoes":        f"{BASE_DOMAIN}/mens/mens-shoes/m_shoes_uko-c",
    "men_new":          f"{BASE_DOMAIN}/mens/mens-new-in/m_new_uko-c",
    "men_black_shoes":  f"{BASE_DOMAIN}/mens/mens-black-shoes/m_blackshoes_uko-c",
    "men_loafers":      f"{BASE_DOMAIN}/mens/mens-shoes/mens-loafers/m_loafers_uko-c",
    "men_brogues":      f"{BASE_DOMAIN}/mens/mens-shoes/mens-brogues/m_brogues_uko-c",
    "men_boatshoes":    f"{BASE_DOMAIN}/mens/mens-shoes/m_boatshoes_uko-c",
    "men_sport":        f"{BASE_DOMAIN}/mens/mens-sport/m_sport_uko-c",
    "men_slippers":     f"{BASE_DOMAIN}/mens/mens-slippers/m_slippers_uko-c",
    # "men_sandals":      f"{BASE_DOMAIN}/mens/mens-sandals/m_sandals_uko-c",
    "men_boots":        f"{BASE_DOMAIN}/mens/mens-boots/m_boots_uko-c",
    "men_walking":      f"{BASE_DOMAIN}/walking-styles/walkingstyles_uko-c",
    "men_sale":         f"{BASE_DOMAIN}/mens/mens-sale/m_sale_uko-c",
    "men_originals":    f"{BASE_DOMAIN}/mens-originals/mo_allstyles_uko-c",
    "clearance":        f"{BASE_DOMAIN}/clearance/clearance_uko-c",
    "last_chance":      f"{BASE_DOMAIN}/last-chance/lastchance_uko-c",
    "seasonal_deals":   f"{BASE_DOMAIN}/seasonal-deals/seasonal_deals_uko-c",
}

# Outlet 站分类页商品列表由前端 JS 渲染，且用「Load more」按钮分页（非 requests 可抓取的 SSR 页面），
# 必须用浏览器打开并点击按钮把该分类下的商品全部加载出来，否则每个分类只能拿到页面初始 HTML 里的极少数链接。
DRIVER_NAME = "clarks_outlet"
MAX_LOAD_MORE_CLICKS = 30
PAGE_LOAD_WAIT = 2
CLICK_WAIT = 1.5
# 同一个 tab 连续点击多个分类的 Load more 后，DOM/JS 堆积会导致 renderer 卡死
# （表现为 "Timed out receiving message from renderer"），所以定期重启 driver，
# 并在单个分类抓取异常时重启后重试一次，避免一个卡死的分类连累后面所有分类。
RECYCLE_DRIVER_EVERY = 5


def _extract_links(html: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    matched = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if LINK_PATTERN_ABS.match(href):
            matched.add(href)
        elif LINK_PATTERN_REL.match(href):
            matched.add(BASE_DOMAIN + href)
    return matched


def _load_all_products(driver) -> int:
    """反复点击 Load more，直到按钮消失（该分类商品已全部加载）"""
    clicks = 0
    while clicks < MAX_LOAD_MORE_CLICKS:
        buttons = driver.find_elements(By.CSS_SELECTOR, 'button[data-testid="loadMoreButton"]')
        if not buttons:
            break
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", buttons[0])
            buttons[0].click()
        except Exception:
            break
        clicks += 1
        time.sleep(CLICK_WAIT)
    return clicks


def _restart_driver():
    quit_driver(DRIVER_NAME)
    return get_driver(DRIVER_NAME, headless=True)


def _scrape_category(driver, url):
    driver.get(url)
    time.sleep(PAGE_LOAD_WAIT)
    clicks = _load_all_products(driver)
    matched = _extract_links(driver.page_source)
    return clicks, matched


def get_outlet_product_links():
    all_links = set()
    driver = get_driver(DRIVER_NAME, headless=True)

    try:
        for i, (category, url) in enumerate(URLS.items(), start=1):
            print(f"📦 正在抓取 OUTLET 分类: {category}")

            if i > 1 and (i - 1) % RECYCLE_DRIVER_EVERY == 0:
                print("  ♻️ 定期重启浏览器，释放累积的内存/DOM 状态")
                driver = _restart_driver()

            try:
                clicks, matched = _scrape_category(driver, url)
            except Exception as e:
                print(f"  ⚠️ 抓取异常，重启浏览器后重试一次：{e}")
                try:
                    driver = _restart_driver()
                    clicks, matched = _scrape_category(driver, url)
                except Exception as e2:
                    print(f"  ❌ 重试仍失败，跳过该分类：{e2}")
                    continue

            print(f"  ✅ 点击 Load more {clicks} 次，抓取 {len(matched)} 条链接")
            all_links.update(matched)
    finally:
        quit_driver(DRIVER_NAME)

    print(f"✅ 总共抓取 OUTLET 链接 {len(all_links)} 条")
    return sorted(all_links)
