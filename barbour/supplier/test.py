import re
import json
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

def extract_js_object_array(js_text: str, var_name: str) -> dict:
    # 支持 Colours 和 Sizes 的 Array 格式
    pattern = re.compile(rf"var {re.escape(var_name)}\s*=\s*\[(.*?)\];", re.DOTALL)
    match = pattern.search(js_text)
    if not match:
        return {}
    raw = match.group(1)
    result = {}
    for line in raw.splitlines():
        kv_match = re.search(rf'{var_name}\[\'(\d+)\'\]\s*=\s*[\'"](.+?)[\'"]', line)
        if kv_match:
            result[kv_match.group(1)] = kv_match.group(2)
    return result

def extract_js_json_object(js_text: str, var_name: str) -> dict:
    # 支持 var stockInfo = { ... };
    pattern = re.compile(rf"var {re.escape(var_name)}\s*=\s*(\{{.*?\}});", re.DOTALL)
    match = pattern.search(js_text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            print(f"❌ JSON 解析失败: {var_name}")
    return {}

def normalize_stock_status(msg: str) -> str:
    return "有货" if "sorry" not in msg.lower() else "无货"

def parse_outdoor_and_country(html: str, url: str, site_name="Outdoor and Country") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    js_text = soup.text

    product_name = soup.title.string.strip() if soup.title else "Unknown Product"
    color_code = None
    if "?c=" in url:
        color_str = url.split("?c=")[-1].split("&")[0].replace("%20", " ").strip().lower()
    else:
        color_str = "unknown"

    colours = extract_js_object_array(js_text, "Colours")
    sizes = extract_js_object_array(js_text, "Sizes")
    stock_info = extract_js_json_object(js_text, "stockInfo")

    # 反向查找 color_code
    for cid, cname in colours.items():
        if cname.strip().lower() == color_str:
            color_code = cid
            break
    if not color_code:
        print(f"❗ 无法识别颜色代码: {color_str}")
        return {}

    offer_list = []
    for key, item in stock_info.items():
        if not key.endswith(f"-{color_code}"):
            continue  # 只保留当前颜色
        size_id = key.split("-")[0]
        size_str = sizes.get(size_id, "")
        size_uk = size_str.split(",")[0].replace("UK:", "").strip()

        price = item.get("priceGbp", 0)
        stock_msg = item.get("stockLevelMessage", "")
        availability = item.get("availability", 0)

        offer_list.append({
            "size": size_uk,
            "price": f"{price:.2f}",
            "stock": normalize_stock_status(stock_msg),
            "can_order": "TRUE" if availability == 1 else "FALSE"
        })

    return {
        "Product Name": product_name,
        "Product Color": colours.get(color_code, color_str.capitalize()),
        "Site": site_name,
        "Product URL": url,
        "Offer List": offer_list
    }

def write_offer_txt(output_path: Path, offer_data: dict):
    if not offer_data:
        return

    lines = [
        f"Product Name: {offer_data['Product Name']}",
        f"Product Color: {offer_data['Product Color']}",
        f"Site: {offer_data['Site']}",
        f"Product URL: {offer_data['Product URL']}",
        f"Offer List:"
    ]
    for offer in offer_data["Offer List"]:
        lines.append(f"{offer['size']} | {offer['price']} | {offer['stock']} | {offer['can_order']}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 写入 TXT: {output_path.name}")

def main():
    # 测试 HTML 文件路径（你刚上传的示例）
    html_file = Path("Men's Barbour Ogston Casual Jacket.htm")
    url = "https://www.outdoorandcountry.co.uk/barbour-heritage-liddesdale-jacket.html?c=Olive"
    output_txt = Path("test_output.txt")

    # 读取 HTML 内容
    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()

    # 调用解析函数
    offer_data = parse_outdoor_and_country(html, url)

    # 写入 TXT
    write_offer_txt(output_txt, offer_data)

if __name__ == "__main__":
    main()
