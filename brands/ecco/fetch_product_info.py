# -*- coding: utf-8 -*-
"""
ECCO 抓取（全新独立版）
- 读取商品链接（支持 http(s) 或本地 .htm 文件）
- 提取：Product Code/Name/Description/Gender/Color/Price/Adjusted Price/Size/Material/Feature/Source URL
- 写出 TXT：使用 clarks_jingya 规范（txt_writer.format_txt）
- 抓取策略：requests 优先；如抓不到关键标题，再回退 Selenium（可关闭）
"""
import os
import re
import json
import time
import traceback
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from html import unescape

# ====== 可按需修改：基础配置 ======
LINKS_FILE = Path(r"D:/TB/Products/ecco/publication/product_links.txt")  # 商品链接列表，每行一个 URL 或本地 .htm 文件路径
OUTPUT_DIR = Path(r"D:/TB/Products/ecco/publication/TXT")               # TXT 输出目录
IMAGE_DIR = Path(r"D:/TB/Products/ecco/publication/images")             # 图片输出目录（可选）
LOG_EVERY = 1

# 下载图片（可选）
DOWNLOAD_IMAGES = False
SKIP_EXISTING_IMAGE = True

# 多线程
MAX_WORKERS = 10
REQUEST_TIMEOUT = 20

# Selenium 回退开关与路径（需要时才用）
ENABLE_SELENIUM_FALLBACK = True
CHROMEDRIVER_PATH = r"D:/Software/chromedriver-win64/chromedriver.exe"

# ====== 不要动：Writer ======
# 依赖你现有的 txt_writer.py（同一工程中）
from txt_writer import format_txt  # 确保该模块中有 format_txt(info, filepath, brand=...)

# ====== 材质关键词（可补充）======
MATERIAL_KEYWORDS = [
    "Leather", "GORE-TEX", "Gore-Tex", "Suede", "Nubuck", "Textile", "Fabric",
    "Canvas", "Mesh", "Synthetic", "Rubber", "PU", "TPU", "EVA", "Wool", "Neoprene"
]

# =============== 基础工具 ===============
def ensure_dirs(*paths: Path):
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

def read_links(file: Path):
    if not file.exists():
        raise FileNotFoundError(f"链接文件不存在: {file}")
    lines = [x.strip() for x in file.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x]

def clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def unique_join(items, sep="; "):
    seen, out = set(), []
    for x in items:
        xx = clean_spaces(x)
        if not xx:
            continue
        low = xx.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(xx)
    return sep.join(out)

def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

# =============== 网络抓取（requests / fallback selenium）===============
def fetch_html(url_or_path: str) -> str:
    """优先 requests；如果是本地文件则直接读取；必要时回退 selenium"""
    if not is_url(url_or_path):
        # 本地文件
        p = Path(url_or_path)
        return p.read_text(encoding="utf-8", errors="ignore")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url_or_path, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
        # 如果没有关键标题块，且允许回退，则尝试 selenium
        if ENABLE_SELENIUM_FALLBACK and ('data-testid="product-card-titleandprice"' not in html):
            try:
                return fetch_html_by_selenium(url_or_path)
            except Exception:
                # selenium 失败就返回 requests 的结果（可能也能解析）
                pass
        return html
    except Exception:
        if ENABLE_SELENIUM_FALLBACK:
            return fetch_html_by_selenium(url_or_path)
        raise

_selenium_lock = threading.Lock()
def fetch_html_by_selenium(url: str) -> str:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    with _selenium_lock:  # 避免并发初始化驱动
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.get(url)
        time.sleep(1.0)  # 轻等待，必要时可调
        return driver.page_source
    finally:
        driver.quit()

# =============== 页面解析 ===============
def extract_title_block(soup: BeautifulSoup):
    """
    解析结构：
    <div data-testid="product-card-titleandprice">
      <h1>
        <p>Men's Leather Gore-Tex Trainer</p>
        ECCO Street 720
      </h1>
    </div>
    返回 (subtitle, main_title)
    """
    h1 = soup.select_one('div[data-testid="product-card-titleandprice"] h1')
    if not h1:
        return "", ""
    p = h1.find("p")
    subtitle = clean_spaces(p.get_text(" ", strip=True)) if p else ""
    # h1 内“直接文本节点”（不含 <p> 的）通常是主标题
    tail_nodes = [t for t in h1.find_all(string=True, recursive=False)]
    main_title = clean_spaces(tail_nodes[0]) if tail_nodes and clean_spaces(tail_nodes[0]) else ""
    return subtitle, main_title

def parse_gender_from_text(text: str) -> str:
    t = text.lower()
    if "women" in t or "women’s" in t or "women's" in t or "ladies" in t:
        return "women"
    if "men" in t or "men’s" in t or "men's" in t:
        return "men"
    if "kid" in t or "junior" in t or "youth" in t:
        return "kids"
    return ""

def parse_materials_from_text(text: str):
    found = []
    for kw in MATERIAL_KEYWORDS:
        if re.search(rf'(?<!\w){re.escape(kw)}(?!\w)', text, re.IGNORECASE):
            # 规范显示（保持 GORE-TEX 原样）
            norm = kw if kw.isupper() else kw.title()
            found.append(norm)
    # 去重保序：按出现位置排序
    idxs = {m: text.lower().find(m.lower()) for m in found}
    found_sorted = sorted(set(found), key=lambda m: idxs[m])
    return found_sorted

def extract_description(soup: BeautifulSoup) -> str:
    # 先从 JSON-LD 取
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "[]")
            if isinstance(data, list):
                for item in data:
                    desc = item.get("description", "")
                    if desc:
                        text = re.sub(r"<[^>]+>", " ", desc)
                        return clean_spaces(unescape(text))
            elif isinstance(data, dict):
                desc = data.get("description", "")
                if desc:
                    text = re.sub(r"<[^>]+>", " ", desc)
                    return clean_spaces(unescape(text))
        except Exception:
            continue
    # 回退：可见描述容器
    node = soup.select_one("div.product-description")
    return clean_spaces(node.get_text(" ", strip=True)) if node else ""

def extract_features(soup: BeautifulSoup) -> str:
    items = []
    for li in soup.select("div.about-this-product__container div.product-description-list ul li"):
        txt = clean_spaces(li.get_text(" ", strip=True))
        if txt:
            items.append(txt)
    return " | ".join(items)

def extract_price(html: str, soup: BeautifulSoup):
    """
    优先解析 onProductPageInit(...)，否则回退 JSON-LD offers
    """
    # 1) JS 钩子
    try:
        m = re.search(r'productdetailctrl\.onProductPageInit\((\{.*?\})\)', html, re.DOTALL)
        if m:
            js = m.group(1).replace("&quot;", '"')
            data = json.loads(js)
            price = float(data.get("Price", 0) or 0)
            adj = float(data.get("AdjustedPrice", 0) or 0)
            return price, adj
    except Exception:
        pass
    # 2) JSON-LD offers
    try:
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            data = json.loads(script.string or "{}")
            if isinstance(data, dict):
                offers = data.get("offers", {})
                if isinstance(offers, dict):
                    p = float(offers.get("price", 0) or 0)
                    return p, 0.0
    except Exception:
        pass
    return 0.0, 0.0

def extract_sizes_and_stock(html: str, soup: BeautifulSoup):
    """
    返回 ["41:有货","42:无货",...]
    """
    # 优先 DOM
    size_div = soup.find("div", class_="size-picker__rows")
    results = []
    if size_div:
        for btn in size_div.find_all("button"):
            label = clean_spaces(btn.get_text(" ", strip=True))
            if not label:
                continue
            # 你原先逻辑：示例里按钮文字可能是 UK 或范围，这里直接把 label 作为 EU 推断不可靠
            # 简化：如果按钮写的就是 EU（常见），直接用；否则尝试数字提取
            eu = re.findall(r"\d{2}", label)
            eu_size = eu[0] if eu else label
            classes = btn.get("class", [])
            soldout = any("soldout" in c.lower() for c in classes)
            status = "无货" if soldout else "有货"
            results.append(f"{eu_size}:{status}")
        if results:
            return results
    # 回退：从 html 里猜（弱化）
    for m in re.finditer(r'>(\d{2})<', html):
        sz = m.group(1)
        if f"{sz}:" not in ";".join(results):
            results.append(f"{sz}:有货")
    return results

def extract_product_code_color(soup: BeautifulSoup):
    """
    页面上通常有类似：
    <div class="product_info__product-number">Product number: 069563 50034</div>
    """
    node = soup.find("div", class_="product_info__product-number")
    if not node:
        raise RuntimeError("未找到商品编码")
    text = clean_spaces(node.get_text(" ", strip=True))
    # 尝试从最后两段连续数字里拼起来
    nums = re.findall(r"(\d{5,6})", text.replace(" ", ""))
    # 有些页面写成 06956350034 一串（6+5）
    if not nums:
        nums = re.findall(r"(\d+)", text)
    joined = "".join(nums)
    # 兜底：去非数字
    joined = re.sub(r"\D+", "", joined)
    if len(joined) < 8:
        # 最少也该有 6+5 位
        raise RuntimeError(f"编码格式异常: {text}")
    # e.g. 06956350034 => code:069563, color:50034
    code = joined[:6]
    color = joined[6:]
    return code + color, code, color

def extract_color_name(soup: BeautifulSoup) -> str:
    node = soup.select_one("span.product_info__color--selected")
    if node:
        return clean_spaces(node.get_text(" ", strip=True))
    # 可能在标题尾部或变体选择里；缺失则 No Data
    return "No Data"

def decide_gender(gender_by_size: str, gender_from_title: str) -> str:
    if gender_from_title in ("men", "women", "kids"):
        return gender_from_title
    if gender_by_size in ("men", "women", "kids"):
        return gender_by_size
    return "unisex"

# =============== 主流程 ===============
def process_one(url: str, idx: int, total: int):
    try:
        html = fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        # --- 编码/颜色码 ---
        product_code_full, code6, color5 = extract_product_code_color(soup)
        color_name = extract_color_name(soup)

        # --- 标题两段 ---
        subtitle, main_title = extract_title_block(soup)
        # 旧结构兜底（老站的 intro-title）
        if not (subtitle or main_title):
            legacy = soup.select_one("span.product_info__intro-title")
            main_title = clean_spaces(legacy.get_text(" ", strip=True)) if legacy else main_title

        # 合并 Product Name
        name_parts = [x for x in [subtitle, main_title] if x]
        product_name = " | ".join(name_parts) if name_parts else "No Data"

        # --- 描述/要点 ---
        description = extract_description(soup)
        feature = extract_features(soup)

        # --- 材质 ---
        materials = []
        materials += parse_materials_from_text(subtitle + " " + main_title)
        # 适度从描述补充（可能包含 outsole/lining 等词，按需取舍）
        if description:
            materials += parse_materials_from_text(description)
        material = unique_join(materials) if materials else "No Data"

        # --- 价格 ---
        price, adjusted = extract_price(html, soup)

        # --- 尺码 + 性别推断 ---
        sizes = extract_sizes_and_stock(html, soup)  # ["41:有货","42:无货"]
        eu_sizes = [s.split(":")[0] for s in sizes if ":" in s]
        gender_by_size = "unisex"
        if any(s.isdigit() and int(s) < 35 for s in eu_sizes):
            gender_by_size = "kids"
        elif any(s in ("45", "46") for s in eu_sizes):
            gender_by_size = "men"
        elif any(s in ("35", "36") for s in eu_sizes):
            gender_by_size = "women"

        gender_from_title = parse_gender_from_text(subtitle + " " + main_title)
        gender = decide_gender(gender_by_size, gender_from_title)

        # --- 组织写入 ---
        info = {
            "Product Code": product_code_full,       # 例如 06956350034
            "Product Name": product_name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color_name,
            "Product Price": price,
            "Adjusted Price": adjusted,
            "Product Material": material,
            "Product Size": ";".join(sizes),
            "Feature": feature,
            "Source URL": url
        }

        ensure_dirs(OUTPUT_DIR)
        out_path = OUTPUT_DIR / f"{product_code_full}.txt"
        # 关键：按 clarks_jingya 规范写入
        format_txt(info, out_path, brand="clarks_jingya")
        if idx % LOG_EVERY == 0:
            print(f"[{idx}/{total}] ✅ TXT 写入：{out_path.name}")

        # --- 图片（可选）---
        if DOWNLOAD_IMAGES:
            ensure_dirs(IMAGE_DIR)
            # 示例：放大规则，如需兼容站点命名可自行扩展
            for img in soup.select("div.product_details__media-item-img img"):
                src = img.get("src") or ""
                if not src:
                    continue
                # 尝试替换更高清尺寸关键词（按你的习惯）
                src_hd = src.replace("DetailsMedium", "ProductDetailslarge3x")
                # 构建文件名：用完整 product_code 前缀 + 顺序
                # 若 URL 自带规范名也可沿用
                pic_name = Path(src_hd.split("?")[0]).name
                pic_path = IMAGE_DIR / pic_name
                if SKIP_EXISTING_IMAGE and pic_path.exists():
                    continue
                try:
                    r = requests.get(src_hd, timeout=REQUEST_TIMEOUT)
                    r.raise_for_status()
                    pic_path.write_bytes(r.content)
                except Exception as e:
                    print(f"⚠️ 图片失败：{src_hd} - {e}")

    except Exception as e:
        print(f"[{idx}/{total}] ❌ 出错：{url}\n{e}\n{traceback.format_exc()}")

def main():
    ensure_dirs(OUTPUT_DIR, IMAGE_DIR)
    links = read_links(LINKS_FILE)
    total = len(links)
    print(f"📦 待处理 {total} 个链接，线程 {MAX_WORKERS}（Selenium 回退：{ENABLE_SELENIUM_FALLBACK}）")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(process_one, url, i+1, total) for i, url in enumerate(links)]
        for _ in as_completed(futures):
            pass
    print("✅ 全部处理完成。")

if __name__ == "__main__":
    main()
