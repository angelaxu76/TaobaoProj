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

# 成人款 UK→EU 映射（保持原来不变）
UK_TO_EU_CM = {
    "3": "35.5", "3.5": "36", "4": "37", "4.5": "37.5", "5": "38",
    "5.5": "39", "6": "39.5", "6.5": "40", "7": "41", "7.5": "41.5",
    "8": "42", "8.5": "42.5", "9": "43", "9.5": "44", "10": "44.5",
    "10.5": "45", "11": "46", "11.5": "46.5", "12": "47"
}

# ✅ 童款（Junior：UK 7–2.5）专用 UK→EU 映射，避免和成人混用
UK_TO_EU_KIDS = {
    "7": "24",  "7.5": "25",
    "8": "25.5","8.5": "26",
    "9": "27",  "9.5": "27.5",
    "10": "28", "10.5": "28.5",
    "11": "29", "11.5": "29.5",
    "12": "30", "12.5": "31",
    "13": "32", "13.5": "32.5",
    "1": "33",  "1.5": "33.5",
    "2": "34",  "2.5": "35"
}

# 这两个目前可以保留给成人逻辑备用（如后续需要）
FEMALE_RANGE = ["3", "3.5", "4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5", "8"]
MALE_RANGE = ["6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12"]


def extract_product_code(url):
    match = re.search(r"/(\d+)-p", url)
    return match.group(1) if match else "unknown"


def extract_material(soup):
    tags = soup.select("li.sc-ac92809-1 span")
    for i in range(0, len(tags) - 1, 2):
        key = tags[i].get_text(strip=True)
        val = tags[i + 1].get_text(strip=True)
        if "Upper Material" in key:
            return val
    return "No Data"

def detect_gender_from_text(text: str) -> str:
    t = text.lower()

    # 先判断童款（kids / youth / toddler / junior）
    if any(k in t for k in ["youth", "kid", "kids", "toddler", "junior", "infant", "girl", "boy"]):
        return "童款"

    # 再判断成人女款
    if "women" in t or "womens" in t or "ladies" in t:
        return "女款"

    # 再判断成人男款
    if "men" in t or "mens" in t:
        return "男款"

    return "未知"


def detect_gender_from_breadcrumb(soup) -> str:
    """
    从 JSON-LD BreadcrumbList 中解析 gender:
    - position == 2 的 name 通常是 mens / womens / kids / boys / girls
    """
    try:
        scripts = soup.find_all("script", type="application/ld+json")
    except Exception:
        return "未知"

    for script in scripts:
        try:
            if not script.string:
                continue
            data = json.loads(script.string)
        except Exception:
            continue

        # 可能有多个 JSON-LD，找 BreadcrumbList 那个
        if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
            items = data.get("itemListElement") or []
            for item in items:
                try:
                    pos = int(item.get("position", 0))
                except (TypeError, ValueError):
                    continue
                if pos == 2:
                    name = (item.get("name") or "").lower()
                    # mens / men
                    if "men" in name:
                        return "男款"
                    # womens / women
                    if "women" in name:
                        return "女款"
                    # kids / boys / girls 这一档都归为童款
                    if any(k in name for k in ["kid", "kids", "boy", "boys", "girl", "girls", "youth", "junior", "infant"]):
                        return "童款"
    return "未知"



def detect_gender(soup, title: str, desc: str, url: str) -> str:
    # ① 先用 title + description 判
    text = f"{title} {desc}"
    gender = detect_gender_from_text(text)
    if gender != "未知":
        return gender

    # ② 判不出来再用 breadcrumb
    gender = detect_gender_from_breadcrumb(soup)
    if gender != "未知":
        return gender

    # ③ 最后可以用 URL 做个兜底（可选）
    u = url.lower()
    if any(k in u for k in ["youth", "kid", "kids", "toddler", "junior", "infant"]):
        return "童款"
    if "women" in u or "womens" in u:
        return "女款"
    if "men" in u or "mens" in u:
        return "男款"

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


# =========================
# ✅ 抽取公共：读取页面上的 UK 尺码按钮 + 有货/无货
# =========================
def build_size_button_map(soup):
    """
    返回形如 {"7": "有货", "7.5": "无货", ...} 的字典（UK 尺码 → 有货/无货）
    """
    size_map = {}
    for btn in soup.find_all("button", {"data-testid": "sizeItem"}):
        uk = btn.get("title", "").strip()
        aria = (btn.get("aria-label") or "").lower()
        sold_out = "currently unavailable" in aria
        size_map[uk] = "无货" if sold_out else "有货"
    return size_map


# =========================
# ✅ 成人款：根据 UK_TO_EU_CM + SIZE_RANGE_CONFIG 生成 SizeMap & SizeDetail
# =========================
def extract_adult_size_stock(soup, gender: str):
    """
    成人款（男款/女款）尺码库存:
    - 使用 UK_TO_EU_CM 做 UK→EU 映射
    - 使用 SIZE_RANGE_CONFIG["clarks"][gender] 作为 EU 尺码顺序
    """
    size_map_uk = build_size_button_map(soup)

    # 从 config 中读取成人 EU 尺码范围（例如 35.5–47）
    eu_range = SIZE_RANGE_CONFIG.get("clarks", {}).get(gender, [])
    size_detail_dict = {}
    size_map_str = {}

    for eu in eu_range:
        matched = [
            uk for uk, status in size_map_uk.items()
            if UK_TO_EU_CM.get(uk) == eu and status == "有货"
        ]
        stock = 3 if matched else 0
        size_map_str[eu] = "有货" if stock > 0 else "无货"
        size_detail_dict[eu] = {"stock_count": stock, "ean": "0000000000000"}

    return size_map_str, size_detail_dict


# =========================
# ✅ 童款（Junior）：只使用 UK 7–2.5 区间（UK_TO_EU_KIDS）
# =========================
def extract_kids_size_stock(soup):
    """
    童款（Kids / Junior）尺码库存:
    - 只处理 UK 7–2.5
    - 使用 UK_TO_EU_KIDS 做 UK→EU 映射
    - EU 尺码范围优先读取 SIZE_RANGE_CONFIG["clarks"]["童款"]，
      如果没有配置，则按映射表的 value 顺序自动推导 24–35。
    """
    size_map_uk = build_size_button_map(soup)

    eu_range = SIZE_RANGE_CONFIG.get("clarks", {}).get("童款")
    if not eu_range:
        # 如果 config 中还没配童款 EU 尺码，就从映射里自动生成一个有序列表
        eu_range = list(dict.fromkeys(UK_TO_EU_KIDS.values()))

    size_detail_dict = {}
    size_map_str = {}

    for eu in eu_range:
        matched = [
            uk for uk, status in size_map_uk.items()
            if UK_TO_EU_KIDS.get(uk) == eu and status == "有货"
        ]
        stock = 3 if matched else 0
        size_map_str[eu] = "有货" if stock > 0 else "无货"
        size_detail_dict[eu] = {"stock_count": stock, "ean": "0000000000000"}

    return size_map_str, size_detail_dict


# =========================
# ✅ 主处理函数
# =========================
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

        # ✅ 先根据标题 + 描述识别男女/童款
        gender = detect_gender(soup, title, desc, url)


        # 折扣价
        discount_price_raw = data.get("offers", {}).get("price", "")
        discount_price = str(discount_price_raw).strip()

        # 原价
        price_tag = soup.find("span", {"data-testid": "wasPrice"})
        if price_tag:
            original_price = (
                price_tag.get_text(strip=True).replace("£", "").strip()
            )
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

        # =========================
        # ✅ 尺码 & 库存：根据 gender 分流
        # =========================
        if gender == "童款":
            size_map_str, size_detail_dict = extract_kids_size_stock(soup)
        else:
            size_map_str, size_detail_dict = extract_adult_size_stock(soup, gender)

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
            "Style Category": style_category,
            "Feature": feature_str,
            "SizeMap": size_map_str,
            "SizeDetail": size_detail_dict,
            "Source URL": url,
        }

    except Exception as e:
        print(f"❌ 错误: {url}，{e}")
        return None


def clarks_fetch_info(links_file=None):
    """
    Clarks Jingya 商品抓取入口。

    :param links_file: 可选，自定义 product_links.txt 路径。
                       为 None 时，使用 config 中的默认 LINK_FILE。
    """
    if links_file is None:
        links_file = LINK_FILE

    print(f"📄 使用链接文件: {links_file}")

    with open(links_file, "r", encoding="utf-8") as f:
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
