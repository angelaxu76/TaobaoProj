import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from pathlib import Path
import time
from config import BARBOUR

# ✅ 页面与文件配置
TARGET_URL = "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-menswear/all-barbour-mens-clothing-footwear.sub?s=i&pt=Coats+%26+Jackets%2cGilets+%26+Waistcoats%2cKnitwear"

BASE_DOMAIN = "https://www.outdoorandcountry.co.uk"
OUTPUT_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
DEBUG_DIR = OUTPUT_FILE.parent / "debug_pages"
DEBUG_FILE = DEBUG_DIR / "debug_auto_scroll_uc_final.html"

# ✅ 自动滚动参数
SCROLL_STEP = 1200          # 每次滚动距离（像素）
SCROLL_PAUSE = 1.5          # 每次滚动等待时间（秒）
STABLE_THRESHOLD = 20        # 连续 N 次商品数不变才结束滚动

# ✅ 滚动并检测是否加载完成
def scroll_like_mouse_until_loaded(driver, step=SCROLL_STEP, pause=SCROLL_PAUSE, stable_threshold=STABLE_THRESHOLD):
    print("⚡ 开始加速滚动直到商品全部加载...")
    actions = ActionChains(driver)

    last_count = 0
    stable_count = 0
    total_scrolls = 0

    while True:
        actions.scroll_by_amount(0, step).perform()
        time.sleep(pause)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        current_count = len(soup.select("a.image"))
        print(f"🌀 滚动 {total_scrolls+1} 次后，商品数: {current_count}")

        if current_count == last_count:
            stable_count += 1
        else:
            stable_count = 0
            last_count = current_count

        if stable_count >= stable_threshold:
            print(f"✅ 商品数量稳定（{current_count}），停止滚动")
            break

        total_scrolls += 1

# ✅ 提取商品链接
def collect_links_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.select("a.image"):
        href = a.get("href", "").strip()
        if href:
            full_url = href if href.startswith("http") else BASE_DOMAIN + href
            links.add(full_url)
    return links

# ✅ 主流程
def outdoorandcountry_fetch_and_save_links():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, headless=False)
    print(f"🚀 正在打开页面: {TARGET_URL}")
    driver.get(TARGET_URL)
    time.sleep(5)

    scroll_like_mouse_until_loaded(driver)

    # 等你确认页面加载完后继续
    print("\n🟡 页面自动滚动完成，如果你还想人工滚几下，请完成后按回车继续")
    input("⏸️ 确认页面加载完成后请按回车继续 >>> ")

    html = driver.page_source
    links = collect_links_from_html(html)

    # 写入链接
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for link in sorted(links):
            f.write(link + "\n")

    # 保存页面快照
    with DEBUG_FILE.open("w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 共提取商品链接: {len(links)} 条")
    print(f"📄 链接保存至: {OUTPUT_FILE}")
    print(f"📝 页面快照保存至: {DEBUG_FILE}")
    driver.quit()


