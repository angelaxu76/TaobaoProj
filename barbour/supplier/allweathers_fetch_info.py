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

# 让 selenium-stealth 可选（没装也能跑）
try:
    from selenium_stealth import stealth
except ImportError:
    def stealth(*args, **kwargs):
        return

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
    options.add_argument("--headless=new")
    options.add_argument(f"--user-data-dir={temp_profile}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # 你可按需添加代理/UA 等

    driver = webdriver.Chrome(options=options)

    # 可选 stealth
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


# ============ 抽取辅助函数 ============

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _infer_gender_from_title(title_or_name: str) -> str:
    t = (title_or_name or "").lower()
    if re.search(r"\b(women|woman|women's|ladies)\b", t):
        return "女款"
    if re.search(r"\b(men|men's|man)\b", t):
        return "男款"
    if re.search(r"\b(kids?|boys?|girls?)\b", t):
        return "童款"
    return "未知"

def _extract_name_and_color(soup: BeautifulSoup) -> tuple[str, str]:
    # 优先 og:title：形如 "Barbour Acorn Women's Waxed Jacket | Olive"
    og = soup.find("meta", {"property": "og:title"})
    if og and og.get("content"):
        txt = og["content"].strip()
        if "|" in txt:
            name, color = map(str.strip, txt.split("|", 1))
            return name, color
        return txt, "Unknown"

    # 其次 document.title
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        t = t.split("|", 1)[0].strip()
        if "–" in t:
            name, color = map(str.strip, t.split("–", 1))
            return name, color
        return t, "Unknown"

    return "Unknown", "Unknown"

def _extract_description(soup: BeautifulSoup) -> str:
    # 1) twitter:description
    m = soup.find("meta", attrs={"name": "twitter:description"})
    if m and m.get("content"):
        desc = _clean_text(m["content"])
        # 去掉其中的 “Key Features …” 等尾注
        desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
        return desc

    # 2) og:description
    m = soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"):
        desc = _clean_text(m["content"])
        return desc

    # 3) JSON-LD ProductGroup.description
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = _clean_text(j.get("description") or "")
            if desc:
                # 截到 “Key Features” 之前
                desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
                return desc
    return "No Data"

def _extract_features(soup: BeautifulSoup) -> str:
    # 寻找 “Key Features & Benefits” 标题后的列表
    h = soup.find(["h2", "h3"], string=re.compile(r"Key\s*Features", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            items = []
            for li in ul.find_all("li"):
                txt = _clean_text(li.get_text(" ", strip=True))
                if txt:
                    items.append(txt)
            if items:
                return " | ".join(items)

    # 退回 JSON-LD description 里“Key Features …\n...（到 Materials 之前）”
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            if "Key" in desc:
                # 抓 Key Features 块
                m = re.search(
                    r"Key\s*Features.*?:\s*(.+?)\s*(Materials\s*&\s*Technical|Frequently|$)",
                    desc, flags=re.I | re.S
                )
                if m:
                    block = m.group(1)
                    # 按换行/项目点切分
                    parts = [ _clean_text(p) for p in re.split(r"[\r\n]+|•|- ", block) ]
                    parts = [p for p in parts if p]
                    if parts:
                        return " | ".join(parts)
    return "No Data"

def _extract_material_outer(soup: BeautifulSoup) -> str:
    # 页面 H2 “Materials & Technical Specifications” 列表中的 Outer
    h = soup.find(["h2", "h3"], string=re.compile(r"Materials\s*&\s*Technical", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                txt = _clean_text(li.get_text(" ", strip=True))
                m = re.match(r"Outer:\s*(.+)", txt, flags=re.I)
                if m:
                    return m.group(1)

    # 退回 JSON-LD description
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            m = re.search(r"Outer:\s*(.+)", desc, flags=re.I)
            if m:
                outer_line = _clean_text(m.group(1))
                # 截断到行尾或分号/换行
                outer_line = re.split(r"[\r\n;]+", outer_line)[0].strip()
                return outer_line
    return "No Data"

def _extract_price(soup: BeautifulSoup) -> float | None:
    # 页面 meta（Shopify）价格
    m = soup.find("meta", {"property": "product:price:amount"})
    if m and m.get("content"):
        try:
            return float(m["content"])
        except Exception:
            pass
    return None


def parse_detail_page(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # 名称 & 颜色
    name, color = _extract_name_and_color(soup)

    # JSON-LD（Shopify ProductGroup）
    script = soup.find("script", {"type": "application/ld+json"})
    if not script:
        raise ValueError("未找到 JSON-LD 数据段")

    data = demjson3.decode(script.string)
    variants = data.get("hasVariant", []) if isinstance(data, dict) else []
    if not variants:
        raise ValueError("❌ 未找到尺码变体")

    # 商品编码（色码含在编码末尾）：如 LWX0752OL51-16 → LWX0752OL51
    first_sku = (variants[0].get("sku") or "")
    base_sku = first_sku.split("-")[0] if first_sku else "Unknown"

    # 尺码/价格/库存
    offer_list = []
    for item in variants:
        sku = item.get("sku", "")
        offer = item.get("offers") or {}
        try:
            price = float(offer.get("price", 0.0))
        except Exception:
            price = 0.0
        availability = offer.get("availability", "")
        stock_status = "有货" if "InStock" in availability else "无货"
        can_order = (stock_status == "有货")
        # UK 尺码在 sku 尾部：LWX0752OL51-16 → UK 16
        size_tail = sku.split("-")[-1] if "-" in sku else "Unknown"
        size = f"UK {re.sub(r'\\s+', ' ', size_tail)}"
        offer_list.append((size, price, stock_status, can_order))

    # 性别/描述/特性/材质/价格
    gender = _infer_gender_from_title(name)
    description = _extract_description(soup)
    features = _extract_features(soup)
    material_outer = _extract_material_outer(soup)
    price_header = _extract_price(soup)

    info = {
        "Product Name": name,
        "Product Gender": gender,
        "Product Description": description,
        "Feature": features,
        "Product Material": material_outer,         # 只写 Outer
        "Product Color": color,
        "Product Color Code": base_sku,
        "Product Price": price_header,              # 页头价（可能等于各尺码价）
        "Site Name": "Allweathers",
        "Product URL": url,
        "Source URL": url,                          # 兼容写入器
        "Offers": offer_list
    }
    return info


def fetch_one_product(url, idx, total):
    print(f"[{idx}/{total}] 抓取: {url}")
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(2.5)
        html = driver.page_source
        driver.quit()

        data = parse_detail_page(html, url)
        code = data["Product Color Code"] or "Unknown"
        txt_path = TXT_DIR / f"{code}.txt"   # 文件名 = 商品编码
        write_supplier_offer_txt(data, txt_path)
        return (url, "✅ 成功")
    except Exception as e:
        return (url, f"❌ 失败: {e}")


def fetch_allweathers_products(max_workers=MAX_WORKERS):
    print(f"🚀 启动 Allweathers 多线程商品详情抓取（线程数: {max_workers}）")
    links = LINK_FILE.read_text(encoding="utf-8").splitlines()
    links = [u.strip() for u in links if u.strip()]
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
