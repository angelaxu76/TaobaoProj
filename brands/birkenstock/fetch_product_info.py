import sys
from pathlib import Path
import re
import json
import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).resolve().parents[2]))

from config import BIRKENSTOCK
from common_taobao.txt_writer import format_txt

# === 配置 ===
HEADERS = {"User-Agent": "Mozilla/5.0"}
LINK_FILE = BIRKENSTOCK["BASE"] / "publication" / "product_links.txt"
TXT_DIR = BIRKENSTOCK["TXT_DIR"]
BRAND = BIRKENSTOCK["BRAND"]

def extract_product_code(soup, url):
    tag = soup.find("span", class_="top-productnumber")
    if tag:
        code = tag.get("data-productnumber", "")
        match = re.search(r"\b(\d{5,7})\b", code)
        if match:
            return match.group(1)

    tag = soup.find("span", class_="product-number-value")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    tag = soup.find("span", class_="product-number")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    tag = soup.find("p", class_="product-number")
    if tag:
        match = re.search(r"\b(\d{5,7})\b", tag.get_text())
        if match:
            return match.group(1)

    match = re.search(r"(\d{5,7})", url)
    return match.group(1) if match else "unknown"

def extract_all_product_codes(soup):
    """提取页面中所有可能的商品编码"""
    return list(set(re.findall(r"\b\d{6,7}\b", soup.text)))

def extract_image_urls(soup):
    urls = [img.get("data-img") for img in soup.find_all("img", class_="zoom-icon") if img.get("data-img")]
    if urls:
        return urls

    script_tags = soup.find_all("script", type="application/ld+json")
    for tag in script_tags:
        try:
            data = json.loads(tag.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product" and "image" in item:
                        img = item["image"]
                        return img if isinstance(img, list) else [img]
            elif isinstance(data, dict) and data.get("@type") == "Product" and "image" in data:
                img = data["image"]
                return img if isinstance(img, list) else [img]
        except Exception:
            continue
    return []

def extract_code_from_image_url(soup):
    img_urls = extract_image_urls(soup)
    if not img_urls:
        return None
    first_url = img_urls[0]
    match = re.search(r"/(\d{5,7})/", first_url)
    return match.group(1) if match else None

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
            continue
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

        # 提取编码
        raw_code = extract_product_code(soup, url)
        img_code = extract_code_from_image_url(soup)

        # ✅ 优先使用图片编码
        if img_code:
            product_code = img_code.zfill(7)
        elif raw_code:
            product_code = raw_code.zfill(7)
        else:
            product_code = "unknown"

        # 提取标题与商品名
        title = soup.title.get_text(strip=True) if soup.title else "No Title"
        name = title.replace("| BIRKENSTOCK", "").strip()

        # 提取结构化描述
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld and json_ld.string:
            try:
                data = json.loads(json_ld.string.strip())
                if isinstance(data, list):
                    data = data[0]
            except Exception:
                data = {}
        else:
            data = {}

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
