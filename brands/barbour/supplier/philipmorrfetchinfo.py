
# -*- coding: utf-8 -*-
"""
Philip Morris Direct | Barbour 商品抓取（最终整合版）

功能：
1. 多线程稳定抓取
2. 自动重建 driver（InvalidSessionId 自动修复）
3. 主 TXT / TXT.problem 分流
4. 自动记录未知颜色 unknown_colors.csv
5. 自动记录所有问题 problem_summary.csv
6. 自动支持颜色前缀去除（Soft Mint → Mint）
7. 完整编码才写入 TXT，不完整写 TXT.problem
8. 提供 generate_color_map_suggestions.py 生成颜色建议
"""

import re
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
import psycopg2

from config import BARBOUR
from common_taobao.ingest.txt_writer import format_txt

# selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    InvalidSessionIdException,
    WebDriverException,
)

try:
    from selenium_stealth import stealth
except ImportError:
    def stealth(*args, **kwargs):
        return


#########################################
# 配置与路径
#########################################

LINKS_FILE: Path = BARBOUR["LINKS_FILES"]["philipmorris"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["philipmorris"]
SITE_NAME = "Philip Morris"
PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]
COLOR_CODE_MAP = BARBOUR["BARBOUR_COLOR_CODE_MAP"]

TXT_DIR.mkdir(parents=True, exist_ok=True)

TXT_PROBLEM_DIR: Path = TXT_DIR.parent / "TXT.problem"
TXT_PROBLEM_DIR.mkdir(parents=True, exist_ok=True)

UNKNOWN_COLOR_FILE = TXT_DIR.parent / "unknown_colors.csv"
PROBLEM_SUMMARY_FILE = TXT_DIR.parent / "problem_summary.csv"

#########################################
# 浏览器管理：线程局部 driver
#########################################

drivers_lock = threading.Lock()
_all_drivers = set()
thread_local = threading.local()


def create_driver(headless=True):
    """
    创建一个独立 Chrome driver（Philip Morris 专用）
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    print("🚗 [get_driver] 创建新的 Chrome driver (PhilipMorris)")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        stealth(
            driver,
            languages=["en-GB", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    except Exception:
        pass

    with drivers_lock:
        _all_drivers.add(driver)

    return driver


def get_driver(headless=True):
    if not hasattr(thread_local, "driver") or thread_local.driver is None:
        thread_local.driver = create_driver(headless=headless)
    return thread_local.driver


def invalidate_current_driver():
    """
    当前线程 driver 崩了 → 移除 + quit + 重建
    """
    d = getattr(thread_local, "driver", None)
    if d:
        with drivers_lock:
            if d in _all_drivers:
                _all_drivers.remove(d)
        try:
            d.quit()
        except Exception:
            pass
    thread_local.driver = None


def shutdown_all_drivers():
    """
    所有线程结束后统一关闭 driver
    """
    with drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except:
                pass
        _all_drivers.clear()


#########################################
# 工具函数
#########################################

def accept_cookies(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except:
        pass


def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|'\\s]+", "_", (name or "")).strip("_")


#########################################
# 颜色处理（含自动识别前缀）
#########################################

def record_unknown_color(style: str, color: str, url: str):
    from datetime import datetime
    with open(UNKNOWN_COLOR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{style},{color},{url},{datetime.now().isoformat(timespec='seconds')}\n")


def record_problem_item(style, color, product_code, reason, url):
    from datetime import datetime
    with open(PROBLEM_SUMMARY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{style},{color},{product_code},{reason},{url},{datetime.now().isoformat(timespec='seconds')}\n")


def map_color_to_code(color: str) -> str | None:
    """
    尝试 3 步：
    1）组合色取第一个
    2）直接匹配配置
    3）去掉 Soft/Ancient/Muted 等前缀后再次匹配
    """
    if not color:
        return None

    s = color.strip().lower()

    if "/" in s:
        s = s.split("/")[0].strip()

    def try_map(text: str):
        for code, names in COLOR_CODE_MAP.items():
            en = (names.get("en") or "").lower()
            if text == en or text in en or en in text:
                return code
        return None

    code = try_map(s)
    if code:
        return code

    prefixes = ["soft ", "muted ", "ancient ", "classic ", "dark ", "light ", "mid ", "deep "]
    for p in prefixes:
        if s.startswith(p):
            base = s[len(p):].strip()
            code = try_map(base)
            if code:
                return code

    return None


#########################################
# 款式编码提取
#########################################

def extract_style_code(html: str) -> str | None:
    text = html or ""

    mpn = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text)
    if mpn:
        raw = mpn.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z0-9]{0,6}$", token):
                return token[:7]

    m = re.search(r"\b([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})\b", text)
    if m:
        return m.group(1)[:7]

    m = re.search(r"\b([A-Z]{3}\d{4})\b", text)
    if m:
        return m.group(1)

    return None


#########################################
# 价格 & 尺码
#########################################

def _clean_price(t: str) -> str:
    if not t:
        return ""
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", t.replace(",", ""))
    return m.group(1) if m else ""


def extract_prices(soup):
    sale = ""
    orig = ""

    for span in soup.select("span.price.price--withTax"):
        sale = _clean_price(span.text)
        break

    for span in soup.select("span.price.price--rrp"):
        orig = _clean_price(span.text)
        break

    if not sale:
        meta = soup.find("meta", {"property": "product:price:amount"})
        if meta:
            sale = meta.get("content") or ""

    if not orig:
        orig = sale

    return orig, sale


def extract_sizes(html):
    soup = BeautifulSoup(html, "html.parser")
    labels = soup.select("label.form-option")
    out = []

    for lb in labels:
        classes = lb.get("class", [])
        if "label-img" in classes:
            continue

        span = lb.find("span", class_="form-option-variant")
        if not span:
            continue

        size = span.text.strip()
        stock = "无货" if "unavailable" in classes else "有货"
        out.append((size, stock))

    return out


def build_size_str(sizes):
    order = []
    agg = {}
    for size, st in sizes:
        if size not in agg:
            agg[size] = st
            order.append(size)
        else:
            if st == "有货":
                agg[size] = "有货"
    return ";".join([f"{s}:{agg[s]}" for s in order])


#########################################
# 数据库匹配
#########################################

def find_product_code_in_db(style: str, color: str, conn, url: str):
    if not style or not color or not conn:
        return None

    color_abbr = map_color_to_code(color)
    if not color_abbr:
        print(f"⚠️ 未找到颜色简写映射：{style} / {color}")
        record_unknown_color(style, color, url)
        return None

    sql = """
        SELECT product_code FROM barbour_products
        WHERE product_code ILIKE %s
        LIMIT 1
    """

    prefix = f"{style}{color_abbr}"
    with conn.cursor() as cur:
        cur.execute(sql, (prefix + "%",))
        row = cur.fetchone()
        if row:
            return row[0]

    # 特例：Sage SG → GN
    if color.lower() == "sage" and color_abbr == "SG":
        alt = f"{style}GN"
        with conn.cursor() as cur:
            cur.execute(sql, (alt + "%",))
            row = cur.fetchone()
            if row:
                return row[0]

    print(f"⚠️ 数据库未匹配到：{style} / {color}")
    return None


#########################################
# 主流程：处理单 URL
#########################################

def process_url(url: str, output_dir: Path):
    """
    处理单个 URL（含自动重试 2 次）
    """

    for attempt in range(2):
        driver = get_driver(headless=True)

        try:
            print(f"\n🌐 抓取({attempt+1}/2): {url}")
            driver.get(url)
            accept_cookies(driver)
            time.sleep(2)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            style = extract_style_code(html) or ""
            name = soup.find("h1", class_="productView-title")
            product_name = name.text.strip() if name else "No Data"

            desc = soup.find("div", id="tab-description")
            product_desc = " ".join(desc.stripped_strings) if desc else "No Data"

            base_orig, base_sale = extract_prices(soup)

            color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
            variants = []

            if color_elems:
                for idx in range(len(color_elems)):
                    color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
                    if idx >= len(color_elems):
                        break

                    elem = color_elems[idx]
                    color = elem.text.strip() or (elem.get_attribute("title") or "No Data")

                    print(f"  🎨 {idx+1}/{len(color_elems)}: {color}")

                    if color == "No Data":
                        continue

                    driver.execute_script("arguments[0].click();", elem)
                    time.sleep(1.3)

                    html_c = driver.page_source
                    soup_c = BeautifulSoup(html_c, "html.parser")

                    orig, sale = extract_prices(soup_c)
                    if not sale:
                        sale = base_sale
                    if not orig:
                        orig = base_orig or sale

                    sizes = extract_sizes(html_c)
                    size_str = build_size_str(sizes)

                    adjusted = sale if sale != orig else ""

                    variants.append({
                        "_style": style,
                        "Product Name": product_name,
                        "Product Description": product_desc,
                        "Product Color": color,
                        "Product Price": orig or sale or "0",
                        "Adjusted Price": adjusted,
                        "Product Size": size_str,
                        "Site Name": SITE_NAME,
                        "Source URL": url,
                    })

            else:
                print("⚠️ 无颜色选项 → 视为单色")
                color = "No Data"
                sizes = extract_sizes(html)
                size_str = build_size_str(sizes)
                adjusted = base_sale if base_sale != base_orig else ""

                variants.append({
                    "_style": style,
                    "Product Name": product_name,
                    "Product Description": product_desc,
                    "Product Color": color,
                    "Product Price": base_orig or base_sale or "0",
                    "Adjusted Price": adjusted,
                    "Product Size": size_str,
                    "Site Name": SITE_NAME,
                    "Source URL": url,
                })

            #########################
            # 写入 TXT 或 TXT.problem
            #########################

            if not variants:
                print("❌ 无变体 → 跳过")
                return

            # DB connection
            conn = None
            try:
                conn = psycopg2.connect(**PGSQL_CONFIG)
                print("✅ 数据库连接成功")
            except:
                print("⚠️ 数据库连接失败 → 全部算问题文件")

            for info in variants:
                style = info.pop("_style") or ""
                color = info["Product Color"]

                product_code = None
                reason = ""

                if style and conn:
                    product_code = find_product_code_in_db(style, color, conn, url)

                if product_code:
                    target_dir = TXT_DIR
                    info["Product Code"] = product_code
                else:
                    # 问题文件
                    target_dir = TXT_PROBLEM_DIR
                    info["Product Code"] = style or "UNKNOWN"
                    reason = "unknown_color" if map_color_to_code(color) is None else "no_db_match"
                    record_problem_item(style, color, info["Product Code"], reason, url)

                fname = sanitize_filename(info["Product Code"]) + ".txt"
                fpath = target_dir / fname
                format_txt(info, fpath, brand="Barbour")

                if target_dir == TXT_DIR:
                    print(f"  ✅ 写入 TXT: {fname}")
                else:
                    print(f"  ⚠️ 写入 TXT.problem: {fname}  ({reason})")

            return  # 本链接成功完成

        except InvalidSessionIdException as e:
            print(f"⚠️ driver 会话失效 → 重建: {e}")
            invalidate_current_driver()
            time.sleep(1)
            continue

        except WebDriverException as e:
            print(f"❌ WebDriver 异常 → 放弃: {e}")
            return

        except Exception as e:
            print(f"❌ 处理失败: {url}\n    {e}")
            return

    return


#########################################
# 批量入口
#########################################

def philipmorris_fetch_info(max_workers=3):
    print(f"LINKS_FILE = {LINKS_FILE}")
    print(f"TXT_DIR    = {TXT_DIR}")

    urls = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u:
                urls.append(u)

    print(f"🚀 启动 Philip Morris 抓取，总 {len(urls)} 条，线程数={max_workers}")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            futures = [exe.submit(process_url, u, TXT_DIR) for u in urls]
            for _ in as_completed(futures):
                pass
    finally:
        shutdown_all_drivers()
        print("🧹 已关闭所有 driver")


#########################################
# main
#########################################

if __name__ == "__main__":
    philipmorris_fetch_info(max_workers=10)
