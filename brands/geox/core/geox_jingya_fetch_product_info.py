
import os
import re
import time
import json
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import SIZE_RANGE_CONFIG, GEOX
from common_taobao.txt_writer import format_txt
from common_taobao.core.category_utils import infer_style_category

PRODUCT_LINK_FILE = GEOX["BASE"] / "publication" / "product_links.txt"
TXT_OUTPUT_DIR = GEOX["TXT_DIR"]
MAX_THREADS = 5
BRAND = "geox"

TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_driver():
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-gcm-driver")
    chrome_options.add_argument("--disable-features=Translate,MediaRouter,AutofillServerCommunication")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def get_html(driver, url):
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.product-id"))
        )
        time.sleep(1)
        return driver.page_source
    except:
        print(f"⚠️ 页面加载失败: {url}")
        return None

def supplement_geox_sizes(size_stock: dict, gender: str) -> dict:
    standard_sizes = SIZE_RANGE_CONFIG.get("geox", {}).get(gender, [])
    for size in standard_sizes:
        if size not in size_stock:
            size_stock[size] = "0"  # 无货
    return size_stock

def detect_gender_by_code(code: str) -> str:
    if not code:
        return "未知"
    code = code.strip().upper()
    if code.startswith("D"):
        return "女款"
    if code.startswith("U"):
        return "男款"
    if code.startswith("J"):
        return "童款"
    return "未知"

def parse_product(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    # 基本信息
    code_tag = soup.select_one("span.product-id")
    code = code_tag.text.strip() if code_tag else "No Data"

    name_tag = soup.select_one("div.sticky-image img")
    name = name_tag["alt"].strip() if name_tag and name_tag.has_attr("alt") else "No Data"

    # 价格（取最大值处理区间价格）
    price_tag = soup.select_one("span.product-price span.value")
    discount_tag = soup.select_one("span.sales.discount span.value")

    def extract_max_price(val):
        if not val:
            return "No Data"
        s = str(val).strip()
        if "-" in s:
            try:
                parts = [float(p.strip()) for p in s.split("-") if p.strip()]
                return f"{max(parts):.2f}"
            except:
                return s
        return s

    full_price_raw = price_tag["content"].strip() if price_tag and price_tag.has_attr("content") else ""
    discount_price_raw = discount_tag["content"].strip() if discount_tag and discount_tag.has_attr("content") else full_price_raw

    original_price = extract_max_price(full_price_raw) or "No Data"
    discount_price = extract_max_price(discount_price_raw) or original_price

    # 颜色 / 材质 / 描述
    color_block = soup.select_one("div.sticky-color")
    color = color_block.get_text(strip=True).replace("Color:", "") if color_block else "No Data"

    materials_block = soup.select_one("div.materials-container")
    material_text = materials_block.get_text(" ", strip=True) if materials_block else "No Data"

    desc_block = soup.select_one("div.product-description div.value")
    description = desc_block.get_text(strip=True) if desc_block else "No Data"

    # 性别
    gender = detect_gender_by_code(code)

    # 尺码库存
    size_blocks = soup.select("div.size-value")
    size_stock = {}
    for sb in size_blocks:
        size = sb.get("data-attr-value") or sb.get("prodsize") or sb.get("aria-label")
        size = size.strip().replace(",", ".") if size else "Unknown"
        available = "1" if "disabled" not in sb.get("class", []) else "0"
        size_stock[size] = available

    size_stock = supplement_geox_sizes(size_stock, gender)

    # === Jingya 模式：输出 SizeMap / SizeDetail ===
    # SizeMap: {"42":"有货","43":"无货", ...}
    # SizeDetail: {"42":{"stock_count":3,"ean":"0000000000000"}, ...}
    size_map = {}
    size_detail = {}
    for eu, flag in size_stock.items():
        has = (str(flag) == "1")
        size_map[eu] = "有货" if has else "无货"
        size_detail[eu] = {"stock_count": 3 if has else 0, "ean": "0000000000000"}

    # 风格分类（通用规则推断）
    style_category = infer_style_category(f"{name} {description}")

    # Feature 占位（GEOX 暂无结构化 features）
    feature_str = "No Data"

    info = {
        "Product Code": code,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": original_price,
        "Adjusted Price": discount_price,
        "Product Material": material_text,
        "Style Category": style_category,
        "Feature": feature_str,
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Source URL": url
    }
    return info

def process_product(url: str):
    driver = create_driver()
    try:
        html = get_html(driver, url)
        if not html:
            return
        info = parse_product(html, url)
        if not info:
            return
        txt_path = TXT_OUTPUT_DIR / f"{info['Product Code']}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        format_txt(info, txt_path, brand=BRAND)
        print(f"✅ 写入成功: {txt_path.name}")
    except Exception as e:
        print(f"❌ 处理失败 {url} → {e}")
    finally:
        driver.quit()

def fetch_all_product_info():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return

    with open(PRODUCT_LINK_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    # 先用一个 driver 进行手动登录，沿用你现有流程
    driver = create_driver()
    if urls:
        driver.get(urls[0])
        print("⏳ 请在新窗口手动登录 GEOX（等待 20 秒）")
        time.sleep(20)
    driver.quit()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_url = {executor.submit(process_product, url): url for url in urls}
        for i, future in enumerate(as_completed(future_to_url), 1):
            url = future_to_url[future]
            try:
                future.result()
            except Exception as e:
                print(f"[{i}] ❌ 异常: {url} → {e}")

    print("\n✅ 所有商品处理完成。")

if __name__ == "__main__":
    fetch_all_product_info()
