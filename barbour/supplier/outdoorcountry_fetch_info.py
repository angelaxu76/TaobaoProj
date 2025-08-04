import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import undetected_chromedriver as uc
from config import BARBOUR
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

def process_url(url, output_dir):
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    # ❗️不要加 headless，会被 Cloudflare 拦截
    driver = uc.Chrome(options=options)

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
    finally:
        driver.quit()

def fetch_outdoor_product_offers_concurrent(max_workers=3):
    links_file = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
    output_dir = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = []
    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                urls.append(url)

    print(f"🔄 启动多线程抓取，总链接数: {len(urls)}，并发线程数: {max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_url, url, output_dir) for url in urls]

        for future in as_completed(futures):
            pass  # 可添加进度显示或异常捕获

if __name__ == "__main__":
    fetch_outdoor_product_offers_concurrent(max_workers=3)

