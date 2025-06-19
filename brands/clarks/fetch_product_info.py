
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from config import CLARKS

LINK_FILE = CLARKS["BASE"] / "publication" / "product_links.txt"
TXT_DIR = CLARKS["TXT_DIR"]
HEADERS = {"User-Agent": "Mozilla/5.0"}

UK_TO_EU_CM = {
    "3": ("35.5", "22.1"), "3.5": ("36", "22.5"), "4": ("37", "22.9"),
    "4.5": ("37.5", "23.3"), "5": ("38", "23.7"), "5.5": ("39", "24.1"),
    "6": ("39.5", "24.5"), "6.5": ("40", "25"), "7": ("41", "25.4"),
    "7.5": ("41.5", "25.7"), "8": ("42", "26"), "8.5": ("42.5", "26.5"),
    "9": ("43", "27"), "9.5": ("44", "27.5"), "10": ("44.5", "28"),
    "10.5": ("45", "28.5"), "11": ("46", "28.9"), "11.5": ("46.5", "29.3"), "12": ("47", "30")
}
FEMALE_UK_RANGE = ["3", "3.5", "4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5", "8"]
MALE_UK_RANGE = ["6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12"]

def extract_product_code(url):
    match = re.search(r'/(\d+)-p', url)
    return match.group(1) if match else "unknown"

def extract_material_info(soup):
    result = {
        "Upper Material": "No Data",
        "Lining Material": "No Data",
        "Sole Material": "No Data",
        "Midsole Material": "No Data",
        "Fastening Type": "No Data",
        "Trims": "No Data",
        "Sock Material": "No Data"
    }
    li_tags = soup.select("li.sc-ac92809-1")
    for li in li_tags:
        spans = li.find_all("span")
        if len(spans) == 2:
            key = spans[0].get_text(strip=True)
            val = spans[1].get_text(strip=True)
            if key in result:
                result[key] = val
    return result

def detect_gender(text):
    text = text.lower()
    if "women" in text:
        return "women"
    elif "men" in text:
        return "men"
    elif "girl" in text:
        return "girl"
    elif "boy" in text:
        return "boy"
    return "unknown"

def process_product_info(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        product_code = extract_product_code(url)
        title = soup.title.get_text(strip=True) if soup.title else "No Title"

        json_ld = soup.find("script", type="application/ld+json")
        json_data = json.loads(json_ld.string) if json_ld else {}
        description = json_data.get("description", "No Description")
        actual_price = json_data.get("offers", {}).get("price", "No Price")

        gender = detect_gender(title + " " + description)
        full_uk_range = FEMALE_UK_RANGE if gender == "women" else MALE_UK_RANGE

        was_price_tag = soup.find("span", {"data-testid": "wasPrice"})
        was_price = was_price_tag.text.strip() if was_price_tag else "No Data"

        material_info = extract_material_info(soup)

        size_status = {}
        for btn in soup.find_all("button", {"data-testid": "sizeItem"}):
            size_uk = btn.get("title", "").strip()
            if size_uk in UK_TO_EU_CM:
                unavailable = "currently unavailable" in btn.get("aria-label", "").lower()
                size_status[size_uk] = "无货" if unavailable else "有货"

        size_stock = []
        for uk in full_uk_range:
            eu_size = UK_TO_EU_CM.get(uk, ("", ""))[0]
            if eu_size:
                status = size_status.get(uk, "无货")
                size_stock.append(f"{eu_size}:{status}")

        TXT_DIR.mkdir(parents=True, exist_ok=True)
        with open(TXT_DIR / f"{product_code}.txt", "w", encoding="utf-8") as f:
            f.write(f"Product Code: {product_code}\n")
            f.write(f"Product Name: {title}\n")
            f.write(f"Product Description: {description}\n")
            f.write(f"Product Gender: {gender}\n")
            f.write(f"Color: No Data\n")
            f.write(f"Original Price: {was_price}\n")
            f.write(f"Actual Price: £{actual_price}\n")
            f.write(f"Product URL: {url}\n")
            for field, value in material_info.items():
                f.write(f"{field}: {value}\n")
            f.write(f"Size Stock (EU): {';'.join(size_stock)}\n")

        print(f"✅ 完成：{product_code}")
    except Exception as e:
        print(f"❌ 失败：{url}，错误：{e}")

def main():
    if not LINK_FILE.exists():
        print(f"❌ 链接文件不存在：{LINK_FILE}")
        return
    with open(LINK_FILE, "r", encoding="utf-8") as f:
        links = [line.strip() for line in f if line.strip()]
    for url in links:
        process_product_info(url)

if __name__ == "__main__":
    main()
