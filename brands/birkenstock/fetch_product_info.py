import sys
from pathlib import Path
import re
import json
import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).resolve().parents[2]))

from config import BIRKENSTOCK
from common_taobao.txt_writer import format_txt

HEADERS = {"User-Agent": "Mozilla/5.0"}
LINK_FILE = BIRKENSTOCK["BASE"] / "publication" / "product_links.txt"
TXT_DIR = BIRKENSTOCK["TXT_DIR"]
BRAND = BIRKENSTOCK["BRAND"]

def extract_product_code(soup, url):
    # ✅ 1. 最新结构：<span class="top-productnumber" data-productnumber="0010272">
    tag = soup.find("span", class_="top-productnumber")
    if tag:
        code = tag.get("data-productnumber", "")
        match = re.search(r"\b(\d{5,7})\b", code)
        if match:
            return match.group(1)

    # ✅ 2. <span class="product-number-value">1029194</span>
    tag = soup.find("span", class_="product-number-value")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    # ✅ 3. <span class="product-number">1021471</span>
    tag = soup.find("span", class_="product-number")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    # ✅ 4. <p class="product-number">Item no. 1234567</p>
    tag = soup.find("p", class_="product-number")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    # ✅ 5. fallback: 从 URL 提取
    match = re.search(r"(\d{5,7})", url)
    return match.group(1) if match else "unknown"



def extract_material(soup):
    h3_tags = soup.find_all("h3", class_=re.compile("heading-2"))
    for h3 in h3_tags:
        if "Upper material" in h3.get_text():
            b_tag = h3.find("b")
            if b_tag:
                return b_tag.get_text(strip=True)
    return "No Data"

def extract_color(soup):
    tag = soup.find("span", class_="selection-text")
    if tag:
        return tag.get_text(strip=True)
    return "No Data"

def extract_sizes(soup):
    EU_SIZES = {
        "35", "36", "37", "38", "39", "40", "41",
        "42", "43", "44", "45", "46", "47", "48", "49", "50"
    }
    sizes = []
    all_tags = soup.find_all("span", class_=re.compile("swatchanchor"))
    for tag in all_tags:
        size = tag.get("data-size", "").strip()
        if size not in EU_SIZES:
            continue  # 🚫 非欧码，跳过
        classes = tag.get("class", [])
        in_stock = "fylin-link" not in " ".join(classes)
        sizes.append(f"{size}:有货" if in_stock else f"{size}:无货")
    return ";".join(sizes) if sizes else "No Data"

def detect_gender(text):
    text = text.lower()
    if "women" in text:
        return "女款"
    elif "men" in text:
        return "男款"
    elif "kids" in text or "girl" in text or "boy" in text:
        return "童款"
    return "未知"

def process_product(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        product_code = extract_product_code(soup, url)
        title = soup.title.get_text(strip=True) if soup.title else "No Title"
        name = title.replace("| BIRKENSTOCK", "").strip()

        json_ld = soup.find("script", type="application/ld+json")
        data = json.loads(json_ld.string)[0] if json_ld and json_ld.string.strip().startswith("[") else json.loads(json_ld.string)

        desc = data.get("description", "No Description")
        price = data.get("offers", {}).get("price", "")
        currency = data.get("offers", {}).get("priceCurrency", "")

        gender = detect_gender(title + " " + desc)
        material = extract_material(soup)
        color = extract_color(soup)
        sizes = extract_sizes(soup)

        return {
            "Product Code": product_code,
            "Product Name": name,
            "Product Description": desc,
            "Product Gender": gender,
            "Product Color": color,
            "Product Price": price,
            "Adjusted Price": price,
            "Product Material": material,
            "Product Size": sizes,
            "Source URL": url
        }

    except Exception as e:
        print(f"❌ 错误: {url}，{e}")
        return None

def main():
    with open(LINK_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        info = process_product(url)
        if info:
            print(f"\n🔍 {url}")
            for k, v in info.items():
                print(f"{k}: {v}")
            filepath = TXT_DIR / f"{info['Product Code']}.txt"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            format_txt(info, filepath, BRAND)
            print(f"✅ 写入: {filepath.name}")

if __name__ == "__main__":
    main()
