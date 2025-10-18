
import os
import re
import time
import json
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import SIZE_RANGE_CONFIG, GEOX
from common_taobao.txt_writer import format_txt
from common_taobao.core.category_utils import infer_style_category


# ===================== 基本配置 =====================
PRODUCT_LINK_FILE = GEOX["BASE"] / "publication" / "product_links.txt"
TXT_OUTPUT_DIR = GEOX["TXT_DIR"]
BRAND = "geox"
MAX_THREADS = 4  # 建议 3~5，过高易触发风控
LOGIN_WAIT_SECONDS = 40  # 手动登录等待时间

TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ===================== WebDriver 创建 =====================
def create_driver(headless: bool = True) -> webdriver.Chrome:
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    # 稳定性/性能参数
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-notifications")
    # 如遇登录依赖图片校验，可注释下一行
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    # 切勿并发复用同一个 user-data-dir（会被加锁）
    driver = webdriver.Chrome(options=chrome_options)
    return driver


# ===================== 会话导出/导入 =====================
def export_session(driver: webdriver.Chrome) -> Dict:
    """导出 cookies + localStorage，供并发线程复用登录态。"""
    cookies = driver.get_cookies()
    ls_items = driver.execute_script(
        """
        const out = {}; 
        for (let i=0; i<localStorage.length; i++){
            const k = localStorage.key(i);
            out[k] = localStorage.getItem(k);
        }
        return out;
        """
    )
    return {"cookies": cookies, "localStorage": ls_items}


def import_session(driver: webdriver.Chrome, session: Dict, base_url: str = "https://www.geox.com/") -> None:
    """将 cookies + localStorage 注入到新 driver。必须先打开同域页面。"""
    driver.get(base_url)

    # 写入 cookies
    for c in session.get("cookies", []):
        to_add = {
            "name": c.get("name"),
            "value": c.get("value"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        }
        if c.get("domain"):
            to_add["domain"] = c["domain"]
        if c.get("expiry"):
            to_add["expiry"] = c["expiry"]
        try:
            driver.add_cookie(to_add)
        except Exception as e:
            print(f"cookie 注入失败 {to_add.get('name')}: {e}")

    # 写入 localStorage
    driver.execute_script("localStorage.clear();")
    for k, v in session.get("localStorage", {}).items():
        driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k, v)


# ===================== 页面抓取/解析 =====================
def get_html(driver: webdriver.Chrome, url: str) -> Optional[str]:
    driver.get(url)
    try:
        # 以商品编号元素为加载完成标记
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.product-id"))
        )
        time.sleep(1)
        return driver.page_source
    except Exception:
        print(f"⚠️ 页面加载失败: {url}")
        return None


def supplement_geox_sizes(size_stock: Dict[str, str], gender: str) -> Dict[str, str]:
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


def parse_product(html: str, url: str) -> Dict:
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
            except Exception:
                return s
        return s

    full_price_raw = price_tag["content"].strip() if price_tag and price_tag.has_attr("content") else ""
    discount_price_raw = discount_tag["content"].strip() if discount_tag and discount_tag.has_attr("content") else full_price_raw

    original_price = extract_max_price(full_price_raw) or "No Data"
    discount_price = extract_max_price(discount_price_raw) or original_price

    # 颜色 / 材质 / 描述
    color_block = soup.select_one("div.sticky-color")
    color = color_block.get_text(strip=True).replace("Color:", "").strip() if color_block else "No Data"

    materials_block = soup.select_one("div.materials-container")
    material_text = materials_block.get_text(" ", strip=True) if materials_block else "No Data"

    desc_block = soup.select_one("div.product-description div.value")
    description = desc_block.get_text(strip=True) if desc_block else "No Data"

    # 性别
    gender = detect_gender_by_code(code)

    # 尺码库存
    size_blocks = soup.select("div.size-value")
    size_stock: Dict[str, str] = {}
    for sb in size_blocks:
        size = sb.get("data-attr-value") or sb.get("prodsize") or sb.get("aria-label")
        size = size.strip().replace(",", ".") if size else "Unknown"
        available = "1" if "disabled" not in sb.get("class", []) else "0"
        size_stock[size] = available

    size_stock = supplement_geox_sizes(size_stock, gender)

    # Jingya 模式：输出 SizeMap / SizeDetail
    size_map: Dict[str, str] = {}
    size_detail: Dict[str, Dict] = {}
    for eu, flag in size_stock.items():
        has = (str(flag) == "1")
        size_map[eu] = "有货" if has else "无货"
        size_detail[eu] = {"stock_count": 3 if has else 0, "ean": "0000000000000"}

    # 风格分类
    style_category = infer_style_category(f"{name} {description}")

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
        "Feature": "No Data",
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Source URL": url,
    }
    return info


# ===================== 主流程（一次登录→多线程复用） =====================
def fetch_all_product_info():
    if not PRODUCT_LINK_FILE.exists():
        print(f"❌ 缺少链接文件: {PRODUCT_LINK_FILE}")
        return

    with open(PRODUCT_LINK_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("⚠️ 链接列表为空")
        return

    # 1) 打开可见浏览器，手动登录一次
    login_driver = create_driver(headless=False)
    login_driver.get(urls[0])
    print(f"⏳ 请在新窗口手动登录 GEOX（等待 {LOGIN_WAIT_SECONDS} 秒）")
    time.sleep(LOGIN_WAIT_SECONDS)

    # 2) 导出当前登录会话
    session = export_session(login_driver)
    login_driver.quit()

    # 3) 多线程：每个线程自行创建 driver → 注入会话 → 抓取
    def worker(url: str):
        driver = create_driver(headless=True)  # 线程内可用 headless 提速
        try:
            import_session(driver, session, base_url="https://www.geox.com/")
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

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_url = {executor.submit(worker, url): url for url in urls}
        for i, future in enumerate(as_completed(future_to_url), 1):
            url = future_to_url[future]
            try:
                future.result()
            except Exception as e:
                print(f"[{i}] ❌ 异常: {url} → {e}")

    print("\n✅ 所有商品处理完成。")


if __name__ == "__main__":
    fetch_all_product_info()
