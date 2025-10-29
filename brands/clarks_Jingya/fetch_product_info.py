import sys
from pathlib import Path
from config import SIZE_RANGE_CONFIG
from common_taobao.core.category_utils import infer_style_category

# ✅ 加入项目根目录
sys.path.append(str(Path(__file__).resolve().parents[2]))

import re
import json
import requests
from bs4 import BeautifulSoup
from config import CLARKS_JINGYA
from common_taobao.ingest.txt_writer import format_txt

HEADERS = {"User-Agent": "Mozilla/5.0"}
LINK_FILE = CLARKS_JINGYA["BASE"] / "publication" / "product_links.txt"
TXT_DIR = CLARKS_JINGYA["TXT_DIR"]
BRAND = CLARKS_JINGYA["BRAND"]

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

def extract_simple_color(name: str) -> str:
    name = name.lower()
    color_keywords = [
        "black", "tan", "navy", "brown", "white", "grey", "off white", "blue",
        "silver", "olive", "cream", "red", "green", "beige", "cola", "pink",
        "burgundy", "taupe", "stone", "bronze", "orange", "walnut", "pewter",
        "plum", "yellow", "rust"
    ]
    for color in color_keywords:
        if color in name:
            return color
    return "No Data"

# === 省略上半部分保持不变 ===

def process_product(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        code = extract_product_code(url)
        title = soup.title.get_text(strip=True) if soup.title else "No Title"
        color_name = extract_simple_color(title)
        name = title.replace("| Clarks UK", "").strip()

        json_ld = soup.find("script", type="application/ld+json")
        data = json.loads(json_ld.string) if json_ld else {}
        desc = data.get("description", "No Description")

        gender = detect_gender(title + " " + desc)
        size_range = FEMALE_RANGE if gender == "女款" else MALE_RANGE

        # 折扣价
        discount_price_raw = data.get("offers", {}).get("price", "")
        discount_price = str(discount_price_raw).strip()

        # 原价
        price_tag = soup.find("span", {"data-testid": "wasPrice"})
        if price_tag:
            original_price = price_tag.get_text(strip=True).replace("£", "").strip()
        else:
            original_price = discount_price  # ✅ fallback 为折扣价

        material = extract_material(soup)

        # ✅ Feature 占位（Clarks 没有结构化 feature）
        feature_str = "No Data"

        # ✅ 提取颜色（通过 JSON）
        try:
            html = r.text
            pattern = r'{"key":"(\d+)",\s*"color\.en-GB":"(.*?)",\s*"image":"(https://cdn\.media\.amplience\.net/i/clarks/[^"]+)"}'
            matches = re.findall(pattern, html)
            for key, color, img_url in matches:
                if key == code:
                    color_name = color
                    break
        except Exception as e:
            print(f"⚠️ 解析颜色出错: {e}")

        # ✅ 提取尺码库存
        size_map = {}
        for btn in soup.find_all("button", {"data-testid": "sizeItem"}):
            uk = btn.get("title", "").strip()
            sold_out = "currently unavailable" in btn.get("aria-label", "").lower()
            size_map[uk] = "无货" if sold_out else "有货"

        eu_range = SIZE_RANGE_CONFIG.get("clarks", {}).get(gender, [])
        size_detail_dict = {}
        size_map_str = {}
        for eu in eu_range:
            # UK => EU 反向映射
            matched = [uk for uk, status in size_map.items() if UK_TO_EU_CM.get(uk) == eu and status == "有货"]
            stock = 3 if matched else 0
            size_map_str[eu] = "有货" if stock > 0 else "无货"
            size_detail_dict[eu] = {"stock_count": stock, "ean": "0000000000000"}

        style_category = infer_style_category(desc)
        return {
            "Product Code": code,
            "Product Name": name,
            "Product Description": desc,
            "Product Gender": gender,
            "Product Color": color_name,
            "Product Price": original_price,
            "Adjusted Price": discount_price,
            "Product Material": material,
            "Style Category": style_category,  # ✅ 新增字段
            "Feature": feature_str,
            "SizeMap": size_map_str,
            "SizeDetail": size_detail_dict,
            "Source URL": url
        }

    except Exception as e:
        print(f"❌ 错误: {url}，{e}")
        return None


def clarks_fetch_info():
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
    clarks_fetch_info()