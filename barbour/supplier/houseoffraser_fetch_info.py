# barbour/supplier/houseoffraser_fetch_info.py

import time
from pathlib import Path
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from datetime import datetime
from config import BARBOUR
from concurrent.futures import ThreadPoolExecutor, as_completed

LINKS_FILE = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)
SITE_NAME = "House of Fraser"

def get_driver():
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")  # 可切换为静默运行
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)

def parse_product_page(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.text.strip()
    product_name = title.split("|")[1].strip() if "|" in title else title

    price_tag = soup.find("span", id="lblSellingPrice")
    price = price_tag.text.replace("\xa3", "").strip() if price_tag else "0.00"

    color_tag = soup.find("span", id="colourName")
    color = color_tag.text.strip() if color_tag else "No Color"

    # 提取尺码列表
    offer_list = []
    size_select = soup.find("select", id="sizeDdl")
    if size_select:
        for option in size_select.find_all("option"):
            size = option.text.strip()
            if not size or "Select Size" in size:
                continue
            stock_qty = option.get("data-stock-qty", "0")
            stock_status = "有货" if stock_qty and stock_qty != "0" else "无货"
            cleaned_size = clean_size(size)
            offer_list.append(f"{cleaned_size}|{price}|{stock_status}|True")

    return {
        "Product Name": product_name,
        "Product Color": color,
        "Site Name": SITE_NAME,
        "Product URL": url,
        "Offer List": offer_list,
        "Updated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def clean_size(size: str) -> str:
    return size.split("(")[0].strip()

def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).rstrip()

def write_txt(info: dict):
    filename = safe_filename(info["Product Name"]) + ".txt"
    path = TXT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Product Name: {info['Product Name']}\n")
        f.write(f"Product Color: {info['Product Color']}\n")
        f.write(f"Site Name: {info['Site Name']}\n")
        f.write(f"Product URL: {info['Product URL']}\n")
        f.write("Offer List:\n")
        for offer in info["Offer List"]:
            f.write(f"  {offer}\n")
        f.write(f"Updated At: {info['Updated At']}\n")

def process_link(url):
    driver = get_driver()
    try:
        driver.get(url)
        time.sleep(6)
        html = driver.page_source
        info = parse_product_page(html, url)
        write_txt(info)
        print(f"✅ 已保存: {info['Product Name']}.txt")
    except Exception as e:
        print(f"❌ 抓取失败: {url}\n{e}\n")
    finally:
        driver.quit()

def fetch_all():
    links = LINKS_FILE.read_text(encoding="utf-8").splitlines()
    print(f"🚀 共需抓取 {len(links)} 个商品链接\n")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_link, url) for url in links]
        for future in as_completed(futures):
            _ = future.result()

if __name__ == "__main__":
    fetch_all()