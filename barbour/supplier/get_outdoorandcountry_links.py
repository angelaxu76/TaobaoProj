import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from pathlib import Path
import time
from config import BARBOUR

# ✅ 配置
TARGET_URL = "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-menswear/all-barbour-mens-clothing-footwear.sub"
BASE_DOMAIN = "https://www.outdoorandcountry.co.uk"
OUTPUT_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
DEBUG_DIR = OUTPUT_FILE.parent / "debug_pages"
DEBUG_FILE = DEBUG_DIR / "debug_manual_scroll_uc.html"

def collect_links_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.select("a.image"):
        href = a.get("href", "").strip()
        if href:
            full_url = href if href.startswith("http") else BASE_DOMAIN + href
            links.add(full_url)
    return links

def outdoorandcountry_fetch_and_save_links():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ✅ 启动 undetected Chrome
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, headless=False)
    print(f"🚀 正在打开页面: {TARGET_URL}")
    driver.get(TARGET_URL)
    time.sleep(8)  # 等待页面 JS 初始化

    print("\n🟡 请手动操作：")
    print("1️⃣ 接受 Cookie（如提示）")
    print("2️⃣ 向下滚动或点击按钮，直到所有商品加载完毕")
    print("🔄 然后回到控制台，按回车继续")
    input("⏸️ 等你准备好后，按回车继续提取商品链接 >>> ")

    html = driver.page_source
    links = collect_links_from_html(html)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for link in sorted(links):
            f.write(link + "\n")

    with DEBUG_FILE.open("w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 共提取商品链接: {len(links)} 条")
    print(f"📄 链接写入: {OUTPUT_FILE}")
    print(f"📝 页面快照保存: {DEBUG_FILE}")
    driver.quit()

