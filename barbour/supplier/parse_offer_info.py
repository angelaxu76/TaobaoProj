
import re
import json
from bs4 import BeautifulSoup
import demjson3

def extract_js_map_array(js_text: str, var_name: str) -> dict:
    pattern = re.compile(rf"{var_name}\[['\"](?P<key>[^'\"]+)['\"]\]\s*=\s*['\"](?P<val>[^'\"]+)['\"];")
    return {m.group("key"): m.group("val") for m in pattern.finditer(js_text)}

def extract_stock_info_dict(js_text: str) -> dict:
    pattern = re.compile(r"var stockInfo\s*=\s*({.*?});\s*", re.DOTALL)
    match = pattern.search(js_text)
    if not match:
        print("❌ 无法找到 stockInfo 段落")
        return {}

    raw = match.group(1)
    try:
        return demjson3.decode(raw)
    except Exception as e:
        print(f"❌ demjson3 解码失败: {e}")
        return {}

import re
import demjson3

def extract_color_code_from_datalayer(js_text: str) -> str:
    try:
        # 匹配 products 数组（只提取产品部分）
        match = re.search(r'"products"\s*:\s*(\[[\s\S]*?\])', js_text)
        if not match:
            print("❌ 未找到 products 段")
            return "Unknown"

        products_str = match.group(1)

        # 解析为 Python 对象
        products = demjson3.decode(products_str)
        if not products or not isinstance(products, list):
            print("❌ products 解码失败")
            return "Unknown"

        first_sku = products[0].get("sku", "")
        match = re.search(r"[A-Z]{2}\d{2}", first_sku)
        if len(first_sku) > 2:
            return first_sku[:-2]  # 去掉最后两位尺码
        if match:
            return first_sku

    except Exception as e:
        print(f"❌ 解析 dataLayer 产品失败: {e}")

    return "Unknown"




def parse_offer_info(html: str, url: str, site_name="Outdoor and Country") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")
    js_text = "\n".join(script.get_text() for script in scripts if script.get_text())

    product_name = soup.title.string.strip() if soup.title else "Unknown Product"

    current_color = "Unknown"
    if "?c=" in url:
        current_color = url.split("?c=")[-1].split("&")[0].replace("%20", " ").capitalize()

    colours = extract_js_map_array(js_text, "Colours")
    sizes_map = extract_js_map_array(js_text, "Sizes")
    stock_info = extract_stock_info_dict(js_text)

    if not stock_info:
        print(f"⚠️ stockInfo 为空: {url}")
        return None

    color_id = next((k for k, v in colours.items() if v.lower() == current_color.lower()), None)
    if not color_id:
        print(f"⚠️ 未找到颜色ID: {current_color}")
        return None

    color_code = extract_color_code_from_datalayer(js_text)

    offers = []
    for key, value in stock_info.items():
        size_id, c_id = key.split("-")
        if c_id != color_id:
            continue
        size_str = sizes_map.get(size_id, size_id)
        uk_size = size_str.split(",")[0].replace("UK:", "").strip()
        price = float(value.get("priceGbp", 0))
        availability = int(value.get("availability", 0))

        stock_status = "有货" if availability > 0 else "无货"
        can_order = availability > 0

        offers.append((uk_size, price, stock_status, can_order))

    return {
        "Product Name": product_name,
        "Product Color": current_color,
        "Product Color Code": color_code,
        "Site Name": site_name,
        "Product URL": url,
        "Offers": offers
    }
