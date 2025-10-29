import re
import time
import json
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from concurrent.futures import ThreadPoolExecutor, as_completed
import undetected_chromedriver as uc
from config import BARBOUR

# ========== 配置 ==========
LINKS_FILE = BARBOUR["LINKS_FILES"]["philipmorris"]
TXT_DIR = BARBOUR["TXT_DIRS"]["philipmorris"]
SITE_NAME = "Philip Morris"
TXT_DIR.mkdir(parents=True, exist_ok=True)

# ========== 浏览器设置 ==========
def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    return uc.Chrome(options=options, version_main=138)

# ========== 工具函数 ==========
def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".")).rstrip()

def extract_price(soup):
    meta = soup.find("meta", {"property": "product:price:amount"})
    return meta["content"].strip() if meta else "0.00"

def extract_product_name(soup):
    tag = soup.find("title")
    return tag.text.strip().split("|")[0].strip() if tag else "No Title"

def normalize_barbour_code(code: str) -> str:
    match = re.search(r"[A-Z]{3}\d{4}[A-Z]{2}\d{2}", code)
    return match.group() if match else code

def write_txt(product_name, color_name, color_code, offer_list, url):
    normalized_code = normalize_barbour_code(color_code)
    filename = safe_filename(f"{normalized_code}.txt")
    filepath = TXT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Product Name: {product_name}\n")
        f.write(f"Product Color: {color_name}\n")
        f.write(f"Product Color Code: {normalized_code}\n")
        f.write(f"Site Name: {SITE_NAME}\n")
        f.write(f"Product URL: {url}\n")
        f.write("Offer List:\n")
        for offer in offer_list:
            f.write(f"  {offer}\n")
        f.write(f"Updated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# ========== 解析当前颜色页面 ==========
def parse_color_variant(html, url, product_name, price, color_name, color_code):
    soup = BeautifulSoup(html, "html.parser")
    labels = soup.select("label.form-option")
    offer_list = []
    for label in labels:
        size = label.find("span", class_="form-option-variant")
        if not size:
            continue
        size_text = size.text.strip()
        stock_status = "无货" if "unavailable" in label.get("class", []) else "有货"
        can_order = "False" if stock_status == "无货" else "True"
        offer_list.append(f"{size_text}|{price}|{stock_status}|{can_order}")

    write_txt(product_name, color_name, color_code, offer_list, url)
    print(f"✅ 写入颜色 {color_name} ({color_code})")

# ========== 主处理逻辑 ==========
def process_link(url, idx, total):
    print(f"[{idx}/{total}] 处理商品: {url}")
    driver = get_driver()
    try:
        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        product_name = extract_product_name(soup)
        price = extract_price(soup)

        # 🔁 提取 MPN 和颜色名称的映射
        color_map = {}
        p_tags = soup.find_all("p")
        for p in p_tags:
            if "MPN:" in p.text and "Colour:" in p.text:
                mpn_list = re.findall(r"MWX\d+[A-Z0-9]+", p.text)
                color_line = re.search(r"Colour:\s*(.*?)<", str(p), re.DOTALL)
                if not color_line:
                    color_line = re.search(r"Colour:\s*(.*?)\\n", p.text, re.DOTALL)
                color_list = []
                if color_line:
                    color_text = color_line.group(1)
                    color_text = color_text.replace("and", ",")
                    color_list = [c.strip() for c in color_text.split(",") if c.strip()]

                if len(mpn_list) == len(color_list):
                    color_map = dict(zip([c.lower() for c in color_list], mpn_list))
                break

        color_labels = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
        for label in color_labels:
            color_name = label.text.strip() or "unknown"
            try:
                driver.execute_script("arguments[0].click();", label)
                time.sleep(2.5)

                color_code = color_map.get(color_name.lower(), "unknown")
                html = driver.page_source
                parse_color_variant(html, url, product_name, price, color_name, color_code)
            except Exception as e:
                print(f"⚠️ 无法点击颜色 {color_name}: {e}")

    except Exception as e:
        print(f"❌ 抓取失败: {url} - {e}")
    finally:
        driver.quit()

# ========== 多线程执行 ==========
def fetch_all():
    links = LINKS_FILE.read_text(encoding="utf-8").splitlines()
    print(f"🚀 共需抓取 {len(links)} 个商品链接\n")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_link, url, idx + 1, len(links)) for idx, url in enumerate(links)]
        for future in as_completed(futures):
            _ = future.result()

if __name__ == "__main__":
    fetch_all()
