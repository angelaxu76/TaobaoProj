import sys
from pathlib import Path
from config import SIZE_RANGE_CONFIG
import re
import json

# ✅ 加入项目根目录
sys.path.append(str(Path(__file__).resolve().parents[2]))

import re
import json
import requests
from bs4 import BeautifulSoup
from config import CLARKS_JINGYA
from common_taobao.txt_writer import format_txt

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
        "black", "tan", "navy", "brown", "white", "grey",
        "blue", "silver", "red", "green", "beige",
        "pink", "burgundy", "orange", "yellow"
    ]
    for color in color_keywords:
        if color in name:
            return color
    return "No Data"

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
        discount_price = data.get("offers", {}).get("price", "")

        gender = detect_gender(title + " " + desc)
        size_range = FEMALE_RANGE if gender == "女款" else MALE_RANGE

        price_tag = soup.find("span", {"data-testid": "wasPrice"})
        original_price = price_tag.get_text(strip=True).replace("\xa3", "") if price_tag else ""

        material = extract_material(soup)

        try:
            html = r.text  # ✅ 添加这行以定义 html 原始源码

            # 使用正则匹配颜色信息
            pattern = r'{"key":"(\d+)",\s*"color\.en-GB":"(.*?)",\s*"image":"(https://cdn\.media\.amplience\.net/i/clarks/[^"]+)"}'
            matches = re.findall(pattern, html)

            print(f"🟢 找到 {len(matches)} 个颜色选项")
            for key, color, img_url in matches:
                print(f"🔹 key: {key}, color: {color}")
                if key == code:
                    color_name = color
                    print(f"✅ 匹配到当前商品颜色: {color_name}")
                    break
            if color_name == "No Data":
                print(f"❌ 未匹配到当前商品编码: {code}")
        except Exception as e:
            print(f"⚠️ 解析颜色出错: {e}")

        size_map = {}
        for btn in soup.find_all("button", {"data-testid": "sizeItem"}):
            uk = btn.get("title", "").strip()
            sold_out = "currently unavailable" in btn.get("aria-label", "").lower()
            size_map[uk] = "无货" if sold_out else "有货"

        sizes = []
        size_detail = []
        eu_range = SIZE_RANGE_CONFIG.get("clarks", {}).get(gender, [])
        for eu in eu_range:
            stock = 3 if eu in [UK_TO_EU_CM.get(k) for k, v in size_map.items() if v == "有货"] else 0
            sizes.append(f"{eu}:{stock}")
            size_detail.append(f"{eu}:{stock}:0000000000000")  # 占位EAN码

        return {
        "Product Code": code,
        "Product Name": name,
        "Product Description": desc,
        "Product Gender": gender,
        "Product Color": color_name,
        "Product Price": original_price,
        "Adjusted Price": discount_price,
        "Product Material": material,
        "Product Size": ";".join(sizes),
        "Product Size Detail": ";".join(size_detail),
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