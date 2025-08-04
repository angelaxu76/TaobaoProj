import time
from pathlib import Path
import undetected_chromedriver as uc
from config import BARBOUR
from bs4 import BeautifulSoup

# 导入解析函数
from barbour.supplier.parse_offer_info import parse_offer_info
from barbour.write_offer_txt import write_offer_txt

def accept_cookies(driver, timeout=8):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except:
        pass

def fetch_outdoor_product_offers():
    links_file = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
    output_dir = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = set()
    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                urls.add(url)

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options)

    for url in sorted(urls):
        try:
            print(f"\n🌐 正在抓取: {url}")
            driver.get(url)
            accept_cookies(driver)
            time.sleep(3)
            html = driver.page_source

            info = parse_offer_info(html, url)
            if info and info["Offers"]:
                filename = f"{info['Product Name'].replace(' ', '_')}_{info['Product Color']}.txt"
                filepath = output_dir / filename
                write_offer_txt(filepath, info)
                print(f"✅ 写入: {filepath.name}")
            else:
                print(f"⚠️ 无库存信息，跳过: {url}")
        except Exception as e:
            print(f"❌ 处理失败: {url}\n    {e}")

    driver.quit()
