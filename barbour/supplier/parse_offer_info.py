import re
import json
from bs4 import BeautifulSoup
import demjson3


def extract_js_map_array(js_text: str, var_name: str) -> dict:
    """提取 Colours['123'] = 'Black'; 样式的数据为字典"""
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







def parse_offer_info(html: str, url: str, site_name="Outdoor and Country") -> dict:
    """从页面 HTML 提取报价信息，结构清晰统一"""
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all("script")
    js_text = "\n".join(script.get_text() for script in scripts if script.get_text())

    product_name = soup.title.string.strip() if soup.title else "Unknown Product"

    # 当前颜色（从 URL 参数 c= 中解析）
    current_color = "Unknown"
    if "?c=" in url:
        current_color = url.split("?c=")[-1].split("&")[0].replace("%20", " ").capitalize()

    # 解析 JS 字典
    colours = extract_js_map_array(js_text, "Colours")
    sizes_map = extract_js_map_array(js_text, "Sizes")
    stock_info = extract_stock_info_dict(js_text)

    if not stock_info:
        print(f"⚠️ stockInfo 为空: {url}")
        return None

    # 找到当前颜色对应的 ID
    color_id = next((k for k, v in colours.items() if v.lower() == current_color.lower()), None)
    if not color_id:
        print(f"⚠️ 未找到颜色ID: {current_color}")
        return None

    # 组合 offer 列表
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
        "Site Name": site_name,
        "Product URL": url,
        "Offers": offers
    }
