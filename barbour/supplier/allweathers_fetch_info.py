# barbour/supplier/allweathers_fetch_info.py

import demjson3
import time
import re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from config import BARBOUR
from barbour.write_offer_txt import write_offer_txt

LINK_FILE = BARBOUR["LINKS_FILES"]["allweathers"]
TXT_DIR = BARBOUR["TXT_DIRS"]["allweathers"]
TXT_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 6  # ✅ 线程数建议 4~8，根据性能调整

def get_driver():
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")  # 可切换为静默运行
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)

def parse_detail_page(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.text.strip()
    clean_title = title.split("|")[0].strip()
    if "–" in clean_title:
        name, color = map(str.strip, clean_title.split("–"))
    else:
        name, color = clean_title, "Unknown"

    script = soup.find("script", {"type": "application/ld+json"})
    if not script:
        raise ValueError("未找到 JSON 数据段")

    data = demjson3.decode(script.string)
    variants = data.get("hasVariant", [])
    if not variants:
        raise ValueError("❌ 未找到尺码变体")

    offer_list = []
    base_sku = variants[0]["sku"].split("-")[0]

    for item in variants:
        sku = item.get("sku", "")
        price = float(item["offers"].get("price", 0.0))
        availability = item["offers"].get("availability", "")
        stock_status = "有货" if "InStock" in availability else "无货"
        can_order = stock_status == "有货"
        size = f"UK {sku.split('-')[-1]}" if "-" in sku else "Unknown"
        offer_list.append((size, price, stock_status, can_order))

    return {
        "Product Name": name,
        "Product Color": color,
        "Product Color Code": base_sku,
        "Site Name": "Allweathers",
        "Product URL": url,
        "Offers": offer_list
    }

# ✅ 每个线程执行的任务
def fetch_one_product(url, idx, total):
    print(f"[{idx}/{total}] 抓取: {url}")
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(1.0)
        html = driver.page_source
        driver.quit()

        data = parse_detail_page(html, url)
        code = data["Product Color Code"]
        txt_path = TXT_DIR / f"{code}.txt"
        write_offer_txt(data, txt_path)
        return (url, "✅ 成功")
    except Exception as e:
        return (url, f"❌ 失败: {e}")

def fetch_allweathers_products(max_workers=6):  # ✅ 设置默认线程数
    print(f"🚀 启动 Allweathers 多线程商品详情抓取（线程数: {max_workers}）")
    links = LINK_FILE.read_text(encoding="utf-8").splitlines()
    total = len(links)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(fetch_one_product, url, idx + 1, total)
            for idx, url in enumerate(links)
        ]

        for future in as_completed(futures):
            url, status = future.result()
            print(f"✅ {status} - {url}")

    print("\n✅ 所有商品抓取完成")

# ✅ 最前面预热，确保驱动已解压，不再重复写文件
def warm_up_chromedriver():
    try:
        driver = get_driver()
        driver.quit()
    except Exception:
        pass


if __name__ == "__main__":
    warm_up_chromedriver()  # ✅ 提前初始化
    fetch_allweathers_products(5)
