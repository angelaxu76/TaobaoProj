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
BASE_DOMAIN = "https://www.outdoorandcountry.co.uk"
OUTPUT_FILE = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
CHROMEDRIVER_PATH = str(BARBOUR["CHROMEDRIVER_PATH"])
DEBUG_DIR = OUTPUT_FILE.parent / "debug_pages"

def outdoorandcountry_fetch_and_save_links():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 可取消注释调试
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=ChromeService(executable_path=CHROMEDRIVER_PATH), options=chrome_options)

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

                # 保存本地 HTML 页面以供调试
                debug_file = DEBUG_DIR / f"debug_page_{section}_{page}.html"
                with debug_file.open("w", encoding="utf-8") as f:
                    f.write(page_source)

                # 提取商品链接（支持相对路径）
                soup = BeautifulSoup(page_source, "html.parser")
                links = []
                for a in soup.select("a.image"):
                    href = a.get("href", "").strip()
                    if href:
                        full_url = href if href.startswith("http") else BASE_DOMAIN + href
                        links.append(full_url)

                if not links:
                    print(f"⚠️ 第 {page} 页无商品，HTML 已保存: {debug_file}")
                    continue  # 跳过当前页，但不终止整个循环

                all_links.update(links)

            except Exception as e:
                print(f"❌ 抓取失败: {e}")

    driver.quit()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n✅ 共抓取链接: {len(all_links)}，写入: {OUTPUT_FILE}")
