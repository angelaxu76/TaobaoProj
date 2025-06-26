import sys
from pathlib import Path

# ✅ 加入项目根目录
sys.path.append(str(Path(__file__).resolve().parents[2]))

import re
import json
import requests
from bs4 import BeautifulSoup
from config import CLARKS
from common_taobao.txt_writer import format_txt

HEADERS = {"User-Agent": "Mozilla/5.0"}
LINK_FILE = CLARKS["BASE"] / "publication" / "product_links.txt"
TXT_DIR = CLARKS["TXT_DIR"]

UK_TO_EU_CM = {
    "3": "35.5", "3.5": "36", "4": "37", "4.5": "37.5", "5": "38",
    "5.5": "39", "6": "39.5", "6.5": "40", "7": "41", "7.5": "41.5",
    "8": "42", "8.5": "42.5", "9": "43", "9.5": "44", "10": "44.5",
    "10.5": "45", "11": "46", "11.5": "46.5", "12": "47"
}

FEMALE_RANGE = ["3", "3.5", "4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5", "8"]
MALE_RANGE = ["6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12"]

def extract_product_code(url):
    match = re.search(r"/(\d+)-p", url)
    return match.group(1) if match else "unknown"

def extract_material(soup):
    tags = soup.select("li.sc-ac92809-1 span")
    for i in range(0, len(tags) - 1, 2):
        key = tags[i].get_text(strip=True)
        val = tags[i+1].get_text(strip=True)
        if "Upper Material" in key:
            return val
    return "No Data"

def detect_gender(text):
    text = text.lower()
    if "women" in text:
        return "女款"
    elif "men" in text:
        return "男款"
    elif "girl" in text or "boy" in text:
        return "童款"
    return "未知"

def process_product(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        code = extract_product_code(url)
        title = soup.title.get_text(strip=True) if soup.title else "No Title"
        name = title.replace("| Clarks UK", "").strip()

        json_ld = soup.find("script", type="application/ld+json")
        data = json.loads(json_ld.string) if json_ld else {}
        desc = data.get("description", "No Description")
        discount_price = data.get("offers", {}).get("price", "")

        gender = detect_gender(title + " " + desc)
        size_range = FEMALE_RANGE if gender == "女款" else MALE_RANGE

        price_tag = soup.find("span", {"data-testid": "wasPrice"})
        original_price = price_tag.get_text(strip=True).replace("\xa3", "") if price_tag else ""

        material = extract_material(soup)

        size_map = {}
        for btn in soup.find_all("button", {"data-testid": "sizeItem"}):
            uk = btn.get("title", "").strip()
            sold_out = "currently unavailable" in btn.get("aria-label", "").lower()
            size_map[uk] = "无货" if sold_out else "有货"

        sizes = []
        for uk in size_range:
            eu = UK_TO_EU_CM.get(uk, "")
            if eu:
                status = size_map.get(uk, "无货")
                sizes.append(f"{eu}:{status}")

        return {
            "Product Code": code,
            "Product Name": name,
            "Product Description": desc,
            "Upper Material": material,
            "Gender": gender,
            "Price": original_price,
            "Adjusted Price": discount_price,
            "Product Size": ";".join(sizes),
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
            format_txt(info, filepath)
            print(f"✅ 写入: {filepath.name}")

if __name__ == "__main__":
    main()
