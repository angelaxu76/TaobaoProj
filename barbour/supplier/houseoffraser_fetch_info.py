# barbour/supplier/houseoffraser_fetch_info.py
# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour
- 抓取逻辑保持不变（parse_product_page → Offer List）
- pipeline 方法名保持不变：process_link(url), fetch_all()
- 统一用 txt_writer.format_txt 写出“同一模板”的 TXT
- 本站无商品编码 => Product Code 固定写 "No Data"
- 尺码：由 Offer List 生成 Product Size / Product Size Detail（不写 SizeMap）
- 女：4–20（偶数）；男：30–50（偶数）；不写 52
"""

import time
from pathlib import Path
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from config import BARBOUR

# ✅ 统一写入：使用项目里的 txt_writer（与其它站点同模板）
from common_taobao.txt_writer import format_txt

LINKS_FILE = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)
SITE_NAME = "House of Fraser"


# ---------------- 浏览器 ----------------

def get_driver():
    options = uc.ChromeOptions()
    # 如需静默运行可打开：
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)


# ---------------- 页面解析（保持你现有逻辑） ----------------

def parse_product_page(html: str, url: str):
    """
    原有解析：返回 {Product Name, Product Color, Site Name, Product URL, Offer List, Updated At}
    Offer List 元素形如: "size|price|stock_status|True"
    """
    soup = BeautifulSoup(html, "html.parser")

    # 标题：一般是 "House of Fraser | <Product Name> | ..."
    title = (soup.title.text or "").strip() if soup.title else ""
    product_name = title.split("|")[1].strip() if "|" in title else title

    # 价格
    price_tag = soup.find("span", id="lblSellingPrice")
    price = price_tag.text.replace("\xa3", "").strip() if price_tag else "0.00"

    # 颜色
    color_tag = soup.find("span", id="colourName")
    raw_color = color_tag.text.strip() if color_tag else "No Color"
    color = clean_color(raw_color)

    # 尺码列表
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
            # 仍保持你原来的 Offer List 字符串格式
            offer_list.append(f"{cleaned_size}|{price}|{stock_status}|True")

    return {
        "Product Name": product_name,
        "Product Color": color,
        "Site Name": SITE_NAME,
        "Product URL": url,
        "Offer List": offer_list,
        "Updated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


# ---------------- 清洗工具 ----------------

def clean_size(size: str) -> str:
    return size.split("(")[0].strip()

def clean_color(color: str) -> str:
    txt = (color or "").strip()
    txt = re.sub(r"\([^)]*\)", "", txt)          # 去括号注释
    txt = re.sub(r"[^\w\s/+-]", " ", txt)        # 去奇怪符号
    txt = re.sub(r"\s+", " ", txt).strip()
    # 去掉含数字的词
    parts = [p for p in txt.split() if not any(c.isdigit() for c in p)]
    base = " ".join(parts) if parts else txt
    return base.strip()

def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).rstrip()

# ------- 尺码标准化（与其它站点同规则；不写 52） -------

WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（不含 52）

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

def _infer_gender_from_name(name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ["women", "women's", "womens", "ladies", "lady"]):
        return "女款"
    if any(k in n for k in ["men", "men's", "mens"]):
        return "男款"
    return "男款"  # 兜底

def _normalize_size(token: str, gender: str) -> str | None:
    s = (token or "").strip().upper()
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    # 先数字
    m = re.findall(r"\d{1,3}", s)
    if m:
        n = int(m[0])
        if gender == "女款" and n in {4,6,8,10,12,14,16,18,20}:
            return str(n)
        if gender == "男款":
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)
            if 28 <= n <= 54:  # 就近容错到 30..50 偶数
                cand = n if n % 2 == 0 else n-1
                cand = max(30, min(50, cand))
                return str(cand)
        return None
    # 再字母
    key = s.replace("-", "").replace(" ", "")
    return ALPHA_MAP.get(key)

def _sort_sizes(keys: list[str], gender: str) -> list[str]:
    if gender == "女款":
        return [k for k in WOMEN_ORDER if k in keys]
    return [k for k in MEN_ALPHA_ORDER if k in keys] + [k for k in MEN_NUM_ORDER if k in keys]

def offers_to_size_lines(offer_list: list[str], gender: str) -> tuple[str, str]:
    """
    Offer List（'size|price|stock|bool'）→
      Product Size: "6:有货;8:有货;..."
      Product Size Detail: "6:1:0000000000000;8:1:0000000000000;..."
    同尺码出现多次时“有货”优先；不输出 SizeMap。
    """
    status = {}
    count = {}
    for row in offer_list or []:
        parts = [p.strip() for p in row.split("|")]
        if len(parts) < 3:
            continue
        raw_size, _price, stock_status = parts[0], parts[1], parts[2]
        norm = _normalize_size(raw_size, gender)
        if not norm:
            continue
        curr = "有货" if stock_status == "有货" else "无货"
        prev = status.get(norm)
        if prev is None or (prev == "无货" and curr == "有货"):
            status[norm] = curr
            count[norm] = 1 if curr == "有货" else 0

    ordered = _sort_sizes(list(status.keys()), gender)
    ps  = ";".join(f"{k}:{status[k]}" for k in ordered)
    psd = ";".join(f"{k}:{count[k]}:0000000000000" for k in ordered)
    return ps, psd


# ---------------- 写入 TXT（统一模板） ----------------

def process_link(url):
    driver = get_driver()
    try:
        driver.get(url)
        time.sleep(6)
        html = driver.page_source

        # 保持原有解析逻辑
        parsed = parse_product_page(html, url)

        # —— 构造统一 info（不依赖商品编码；Product Code 固定 No Data）——
        gender = _infer_gender_from_name(parsed.get("Product Name", ""))
        ps, psd = offers_to_size_lines(parsed.get("Offer List", []), gender)

        info = {
            "Product Code": "No Data",                # 本站无编码 → 固定 No Data
            "Product Name": parsed.get("Product Name", "No Data"),
            "Product Description": "No Data",
            "Product Gender": gender,
            "Product Color": parsed.get("Product Color", "No Data"),
            "Product Price": None,
            "Adjusted Price": None,
            "Product Material": "No Data",
            "Style Category": "",                     # 交给 txt_writer 推断
            "Feature": "No Data",
            "Product Size": ps,                       # 两行尺码（不写 SizeMap）
            "Product Size Detail": psd,
            "Site Name": SITE_NAME,
            "Source URL": parsed.get("Product URL", url),
            "Brand": "Barbour",
        }

        # 文件名：本站无编码 → 用 名称_颜色
        safe_name  = safe_filename(info["Product Name"])
        safe_color = safe_filename(info["Product Color"])
        filename = f"{safe_name}_{safe_color}.txt"
        txt_path = TXT_DIR / filename

        # ✅ 统一模板写入
        format_txt(info, txt_path, brand="Barbour")
        print(f"✅ 已写入: {txt_path.name}")

    except Exception as e:
        print(f"❌ 抓取失败: {url}\n{e}\n")
    finally:
        driver.quit()


def fetch_all():
    links = [u.strip() for u in LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"🚀 共需抓取 {len(links)} 个商品链接\n")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_link, url) for url in links]
        for future in as_completed(futures):
            _ = future.result()


if __name__ == "__main__":
    fetch_all()
