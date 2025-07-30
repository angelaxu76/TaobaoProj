
import os
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from config import BARBOUR
from common_taobao.txt_writer import format_txt

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
}

def extract_product_info_from_html(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    # 名称
    name = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product" and "name" in data:
                name = data["name"].strip()
                break
        except:
            continue

    # SKU
    sku = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product" and "sku" in data:
                sku = data["sku"].strip()
                break
        except:
            continue

    # 描述
    desc_tag = soup.find("div", {"id": "collapsible-description-1"})
    description = desc_tag.get_text(separator=" ", strip=True).replace(f"SKU: {sku}", "") if desc_tag else "No Data"

    # Feature
    features_tag = soup.find("div", class_="care-information")
    features = features_tag.get_text(separator=" | ", strip=True) if features_tag else "No Data"

    # 价格
    price_tag = soup.select_one("span.sales span.value")
    price = price_tag["content"] if price_tag and price_tag.has_attr("content") else "0"

    # 颜色
    color_tag = soup.select_one("span.selected-color")
    color = color_tag.get_text(strip=True).replace("(", "").replace(")", "") if color_tag else "No Data"

    # 尺码
    size_buttons = soup.select("div.size-wrapper button.size-button")
    size_map = {btn.get_text(strip=True): "有货" for btn in size_buttons} if size_buttons else {}

    info = {
        "Product Code": sku,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": "未知",
        "Product Color": color,
        "Product Price": price,
        "Adjusted Price": price,
        "Product Material": "No Data",
        "Feature": features,
        "SizeMap": size_map,
        "Source URL": url
    }
    return info

def fetch_and_write_txt():
    links_file = BARBOUR["LINKS_FILE"]
    txt_output_dir = BARBOUR["TXT_DIR"]
    os.makedirs(txt_output_dir, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"📄 共 {len(urls)} 个商品页面待解析...")

    for idx, url in enumerate(urls, 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            info = extract_product_info_from_html(resp.text, url)

            txt_path = Path(txt_output_dir) / f"{info['Product Code']}.txt"
            format_txt(info, txt_path, brand="barbour")
            print(f"✅ [{idx}/{len(urls)}] 写入成功：{txt_path.name}")
        except Exception as e:
            print(f"❌ [{idx}/{len(urls)}] 失败：{url}，错误：{e}")

if __name__ == "__main__":
    fetch_and_write_txt()
