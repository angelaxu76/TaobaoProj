
import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ECCO, ensure_all_dirs
from common_taobao.txt_writer import format_txt  # ✅ 使用标准写入

# ========== 全局路径 & 参数 ==========
PRODUCT_LINKS_FILE = ECCO["BASE"] / "publication" / "product_links.txt"
TXT_DIR = ECCO["TXT_DIR"]
IMAGE_DIR = ECCO["IMAGE_DIR"]
CHROMEDRIVER_PATH = "D:/Software/chromedriver-win64/chromedriver.exe"
MAX_THREADS = 10
WAIT = 0
DELAY = 0.5

ensure_all_dirs(TXT_DIR, IMAGE_DIR)

DOWNLOAD_IMAGE = False
SKIP_EXISTING_IMAGE = True

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)

def size_to_eu(uk_size):
    uk_to_eu = {
        "2.5-3": "35", "3.5-4": "36", "4.5": "37", "5-5.5": "38",
        "6": "39", "6.5-7": "40", "7.5": "41", "8-8.5": "42",
        "9-9.5": "43", "10": "44", "10.5-11": "45", "11.5": "46"
    }
    return uk_to_eu.get(uk_size)

# ===== 在文件顶部现有 import 下方补充 =====
from html import unescape
import re
import json

def extract_description_from_soup(soup):
    """优先用 JSON-LD 的 description（更完整、少换行），否则退回页面可见描述。"""
    # JSON-LD：<script type="application/ld+json" data-schemaorgproducts="true"> [...]
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "[]")
            if isinstance(data, list) and data:
                desc_html = data[0].get("description", "")
                if desc_html:
                    # 去 HTML 标签与实体
                    text = re.sub(r"<[^>]+>", " ", desc_html)
                    text = re.sub(r"\s+", " ", unescape(text)).strip()
                    if text:
                        return text
        except Exception:
            pass
    # 退回可见描述
    node = soup.select_one("div.product-description")
    return node.get_text(strip=True) if node else ""

def extract_features_from_soup(soup):
    """抓 Features & Benefits 列表，拼接成一句；抓不到返回空字符串。"""
    items = []
    for li in soup.select("div.about-this-product__container div.product-description-list ul li"):
        txt = li.get_text(strip=True)
        if txt:
            items.append(txt)
    # 统一用中文竖线或分号拼接，便于入库后再拆分
    return " | ".join(items)


def extract_sizes_and_stock_status(html):
    soup = BeautifulSoup(html, "html.parser")
    size_div = soup.find("div", class_="size-picker__rows")
    if not size_div:
        return []
    results = []
    for btn in size_div.find_all("button"):
        uk_size = btn.text.strip()
        eu_size = size_to_eu(uk_size)
        if not eu_size:
            continue
        is_soldout = "size-picker__item--soldout" in btn.get("class", [])
        status = "无货" if is_soldout else "有货"
        results.append(f"{eu_size}:{status}")
    return results

def extract_price_info(html):
    try:
        match = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if not match:
            return 0.0, 0.0
        json_text = match.group(1).replace("&quot;", '"')
        data = json.loads(json_text)
        return data.get("Price", 0.0), data.get("AdjustedPrice", 0.0)
    except:
        return 0.0, 0.0

def process_product(url, idx, total):
    driver = None
    try:
        print(f"\n🔍 ({idx}/{total}) 正在处理: {url}")
        driver = create_driver()
        driver.get(url)
        time.sleep(WAIT)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        code_info = soup.find('div', class_='product_info__product-number')
        if not code_info:
            raise Exception("未找到编码")
        product_code = code_info.text.strip().split()[2]
        code, color = product_code[:6], product_code[6:]
        #formatted_code = f"{code}-{color}"

        product_name = soup.select_one("span.product_info__intro-title").get_text(strip=True)
        description = soup.select_one("div.product-description").get_text(strip=True)
        color_name = soup.select_one("span.product_info__color--selected").get_text(strip=True)
        #gender = "women" if "women" in url.lower() else ("men" if "men" in url.lower() else "unisex")



        price, adjusted_price = extract_price_info(driver.page_source)
        material = "No Data"
        sizes = []
        try:
            sizes = extract_sizes_and_stock_status(driver.page_source)
        except Exception as e:
            print(f"⚠️ 提取尺码失败: {e}")

        eu_sizes = [s.split(":")[0] for s in sizes if ":" in s]
        gender = "unisex"
        if any(s for s in eu_sizes if s.isdigit() and int(s) < 35):
            gender = "kids"
        elif any(s for s in eu_sizes if s in ("45", "46")):
            gender = "men"
        elif any(s for s in eu_sizes if s in ("35", "36")):
            gender = "women"

        description = extract_description_from_soup(soup)
        feature = extract_features_from_soup(soup)
        info = {
            "Product Code": product_code,
            "Product Name": product_name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color_name,
            "Product Price": price,
            "Adjusted Price": adjusted_price,
            "Product Material": material,
            "Product Size": ";".join(sizes),
            "Feature": feature,             # ★ 新增：写入要点
            "Source URL": url
        }

        filepath = TXT_DIR / f"{product_code}.txt"
        format_txt(info, filepath,brand="ecco")
        print(f"📄 信息保存: {filepath.name}")

        if DOWNLOAD_IMAGE:
            for img in soup.select("div.product_details__media-item-img img"):
                if "src" not in img.attrs:
                    continue
                img_url = img["src"].replace("DetailsMedium", "ProductDetailslarge3x")
                match = re.search(r'/([0-9A-Za-z-]+-(?:o|m|b|s|top_left_pair|front_pair))\.webp', img_url)
                img_code = match.group(1) if match else product_code
                img_path = IMAGE_DIR / f"{img_code}.webp"
                if SKIP_EXISTING_IMAGE and img_path.exists():
                    print(f"✅ 已存在图片，跳过: {img_path.name}")
                    continue
                try:
                    with open(img_path, "wb") as f:
                        f.write(requests.get(img_url, timeout=10).content)
                    print(f"🖼️ 图片: {img_path.name}")
                    time.sleep(DELAY)
                except Exception as e:
                    print(f"❌ 图片失败: {img_url} - {e}")

    except Exception as e:
        print(f"❌ 错误: {url} - {e}")
    finally:
        if driver:
            driver.quit()

def ecco_fetch_info():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 商品链接文件不存在: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    print(f"\n📦 共 {total} 条商品，线程数: {MAX_THREADS}")
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(process_product, url, i + 1, total) for i, url in enumerate(urls)]
        for _ in as_completed(futures):
            pass
    print("\n✅ ECCO 商品信息与图片处理完毕！")

if __name__ == "__main__":
    ecco_fetch_info()
