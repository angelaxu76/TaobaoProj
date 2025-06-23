import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path
from config import CAMPER
from common_taobao.txt_writer import format_txt

TXT_DIR = CAMPER["TXT_DIR"]
LINKS_FILE = CAMPER["LINKS_FILE"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}
WAIT = 1

TXT_DIR.mkdir(parents=True, exist_ok=True)

def parse_product_page(url: str) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 请求失败: {url}，错误: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # 🧩 你需要根据页面结构解析数据字段：
    try:
        product_code = url.split("/")[-1].split("-")[0]  # 示例处理
        name = soup.find("h1").text.strip()
        description = soup.find("div", class_="product-description").get_text(strip=True)
        upper_material = "No Data"  # 你可以解析真实数据
        color = "No Data"

        return {
            "Product Code": product_code,
            "Product Name": name,
            "Product Description": description,
            "Upper Material": upper_material,
            "Color": color,
            "Product URL": url
        }
    except Exception as e:
        print(f"❌ 解析失败: {url}，错误: {e}")
        return {}

def main():
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        urls = list(set(line.strip() for line in f if line.strip()))

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] 正在处理: {url}")
        info = parse_product_page(url)
        if info:
            product_code = info.get("Product Code", f"unknown_{i}")
            filepath = TXT_DIR / f"{product_code}.txt"
            format_txt(info, filepath)
        time.sleep(WAIT)

    print("\n✅ 所有商品信息已抓取并写入 TXT")

if __name__ == "__main__":
    main()
