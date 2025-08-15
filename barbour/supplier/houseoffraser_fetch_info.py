# barbour/supplier/houseoffraser_fetch_info.py
# -*- coding: utf-8 -*-
"""
抓取 House of Fraser 的 Barbour 商品，解析名称/颜色/尺码库存，
并调用通用匹配器 barbour.match_resolver 解析唯一 color_code。
成功则用 color_code 命名 TXT 文件；否则打印候选日志并回退。
"""

import time
from pathlib import Path
import re
import psycopg2
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from datetime import datetime
from config import BARBOUR
from concurrent.futures import ThreadPoolExecutor, as_completed

# ★ 新增：引入通用匹配器
from barbour.match_resolver import resolve_color_code, debug_log

# ---------------- 基本配置 ----------------

LINKS_FILE = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)
SITE_NAME = "House of Fraser"


# ---------------- 浏览器 ----------------

def get_driver():
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")  # 如需静默运行取消注释
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, use_subprocess=True)


# ---------------- 页面解析 ----------------

def parse_product_page(html: str, url: str):
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
            # 你原有格式：size|price|stock_status|True
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
    """去掉括号/数字等噪音，做基本清洗"""
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


# ---------------- 写入 TXT ----------------

def write_txt(info: dict):
    """
    若 info 含 Product Color Code，则用其命名文件；否则退回到 名称+颜色。
    文件内容包含 Product Color Code 行，便于后续导入 offers。
    """
    code = info.get("Product Color Code")
    if code:
        filename = f"{code}.txt"
    else:
        filename = safe_filename(f"{info['Product Name']} {info['Product Color']}") + ".txt"

    path = TXT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Product Name: {info['Product Name']}\n")
        f.write(f"Product Color: {info['Product Color']}\n")
        f.write(f"Product Color Code: {code if code else 'No Data'}\n")
        f.write(f"Site Name: {info['Site Name']}\n")
        f.write(f"Product URL: {info['Product URL']}\n")
        f.write("Offer List:\n")
        for offer in info["Offer List"]:
            f.write(f"  {offer}\n")
        f.write(f"Updated At: {info['Updated At']}\n")


# ---------------- 抓取流程 ----------------

def process_link(url):
    driver = get_driver()
    conn = None
    try:
        driver.get(url)
        time.sleep(6)
        html = driver.page_source
        info = parse_product_page(html, url)

        # 连接数据库并调用通用匹配器解析 color_code
        try:
            conn = psycopg2.connect(**BARBOUR["PGSQL_CONFIG"])
            res = resolve_color_code(conn, info["Product Name"], info["Product Color"])
            # 打印 Top-K 候选或成功信息
            debug_log(info["Product Name"], info["Product Color"], res)

            if res.status == "matched":
                info["Product Color Code"] = res.color_code
        except Exception as db_e:
            print(f"❌ 数据库匹配错误：{db_e}")

        write_txt(info)
        if info.get("Product Color Code"):
            print(f"✅ 已保存: {info['Product Color Code']}.txt")
        else:
            print(f"📝 已保存(无编码): {info['Product Name']} {info['Product Color']}.txt")
    except Exception as e:
        print(f"❌ 抓取失败: {url}\n{e}\n")
    finally:
        try:
            if conn:
                conn.close()
        except:
            pass
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
