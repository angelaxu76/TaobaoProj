from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import time
from config import BARBOUR

BASE_URLS = {
    "men": "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-menswear/all-barbour-mens-clothing-footwear.sub?s=i&page={}",
    "women": "https://www.outdoorandcountry.co.uk/shop-by-brand/barbour/barbour-womenswear/womens-barbour-clothing-footwear-accessories.sub?s=i&page={}"
}

TOTAL_PAGES = 50
WAIT = 2
OUTPUT_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
CHROMEDRIVER_PATH = str(BARBOUR["CHROMEDRIVER_PATH"])
DEBUG_DIR = OUTPUT_FILE.parent / "debug_pages"

def outdoorandcountry_fetch_and_save_links():
    chrome_options = Options()
    # ✅ 调试时可注释掉 headless
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=ChromeService(executable_path=CHROMEDRIVER_PATH), options=chrome_options)

    # ✅ 启用 Stealth 模式绕过 Cloudflare 检测
    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    all_links = set()
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    for section in BASE_URLS:
        for page in range(1, TOTAL_PAGES + 1):
            url = BASE_URLS[section].format(page)
            print(f"🌐 抓取第 {page} 页: {url}")
            try:
                driver.get(url)
                time.sleep(WAIT)
                page_source = driver.page_source

                # ✅ 保存本地调试 HTML
                debug_file = DEBUG_DIR / f"debug_page_{section}_{page}.html"
                with debug_file.open("w", encoding="utf-8") as f:
                    f.write(page_source)

                # ✅ 解析商品链接
                soup = BeautifulSoup(page_source, "html.parser")
                links = [
                    a.get("href").strip()
                    for a in soup.select("a.image")
                    if a.get("href", "").startswith("http")
                ]
                if not links:
                    print(f"⚠️ 第 {page} 页无商品，HTML 已保存: {debug_file}")
                    break
                all_links.update(links)
            except Exception as e:
                print(f"❌ 抓取失败: {e}")

    driver.quit()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")
    print(f"\n✅ 共抓取链接: {len(all_links)}，写入: {OUTPUT_FILE}")
