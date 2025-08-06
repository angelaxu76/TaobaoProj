# barbour/supplier/allweathers_fetch_info.py

import os
import re
import time
import json
import demjson3
import tempfile
from bs4 import BeautifulSoup
from config import BARBOUR
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium_stealth import stealth
from barbour.barbouir_write_offer_txt import write_supplier_offer_txt
from concurrent.futures import ThreadPoolExecutor, as_completed

# 全局路径
LINK_FILE = BARBOUR["LINKS_FILES"]["allweathers"]
TXT_DIR = BARBOUR["TXT_DIRS"]["allweathers"]
TXT_DIR.mkdir(parents=True, exist_ok=True)

# 线程数
MAX_WORKERS = 6


def get_driver():
    temp_profile = tempfile.mkdtemp()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # ✅ 静默模式不弹窗
    options.add_argument(f"--user-data-dir={temp_profile}")  # ✅ 每线程独立配置
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def parse_detail_page(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # ✅ 从 meta og:title 提取颜色
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        og_text = og_title["content"].strip()
        if "|" in og_text:
            name, color = map(str.strip, og_text.split("|"))
        else:
            name, color = og_text.strip(), "Unknown"
    else:
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


def fetch_one_product(url, idx, total):
    print(f"[{idx}/{total}] 抓取: {url}")
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(2.5)
        html = driver.page_source
        driver.quit()

        data = parse_detail_page(html, url)
        code = data["Product Color Code"]
        txt_path = TXT_DIR / f"{code}.txt"
        write_supplier_offer_txt(data, txt_path)
        return (url, "✅ 成功")
    except Exception as e:
        return (url, f"❌ 失败: {e}")


def fetch_allweathers_products(max_workers=MAX_WORKERS):
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
            print(f"{status} - {url}")

    print("\n✅ 所有商品抓取完成")


if __name__ == "__main__":
    fetch_allweathers_products()
