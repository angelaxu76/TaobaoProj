# barbour_fetch_info.py
# -*- coding: utf-8 -*-

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

from config import BARBOUR
from common_taobao.txt_writer import format_txt              # ✅ 复用你已有的鲸芽写入器
# 如果你的 txt_writer 在 common_taobao 目录：
# from common_taobao.txt_writer import format_txt

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# -------- 工具函数 --------

def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def _extract_gender_from_html(html: str) -> str:
    """
    从页面里的 gtmAnalytics（或类似数据层）提取性别关键词，落到：男款/女款/童款/未知
    """
    m = re.search(r'"item_category"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    gender_raw = m.group(1).strip().lower() if m else ""

    mapping = {
        "womens": "女款", "women": "女款", "ladies": "女款",
        "mens": "男款", "men": "男款",
        "kids": "童款", "children": "童款", "child": "童款",
        "unisex": "通用",
    }
    return mapping.get(gender_raw, "未知")

def _extract_material_from_features(features_text: str) -> str:
    """
    从 features 文本中尽量抽取主体材质（xx% xxx），没有就返回 No Data。
    """
    if not features_text:
        return "No Data"
    text = features_text.replace("\n", " ").replace("\r", " ")
    # 常见的 “65% Polyester 35% Cotton” / “100% Cotton”
    mats = re.findall(r"\b\d{1,3}%\s+[A-Za-z][A-Za-z \-]*", text)
    if mats:
        return " / ".join(mats[:2])
    return "No Data"

# -------- 解析核心 --------

def extract_product_info_from_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # 名称 / SKU 从 ld+json 里拿（Barbour 官网常见）
    name = "No Data"
    sku = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        data = _safe_json_loads(script.string or "")
        if isinstance(data, dict) and data.get("@type") == "Product":
            if data.get("name"):
                name = str(data["name"]).strip()
            if data.get("sku"):
                sku = str(data["sku"]).strip()
            break

    # 描述
    desc_tag = soup.find("div", {"id": "collapsible-description-1"})
    description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else "No Data"
    if sku and sku != "No Data":
        # 有些页面会把 “SKU: XXX” 混在描述里，清一下
        description = description.replace(f"SKU: {sku}", "").strip() or "No Data"

    # Features（含保养/材质等）
    features_tag = soup.find("div", class_="care-information")
    features = features_tag.get_text(separator=" | ", strip=True) if features_tag else "No Data"

    # 价格（页面通常有 meta content 或可见价格）
    price_tag = soup.select_one("span.sales span.value")
    price = price_tag["content"] if price_tag and price_tag.has_attr("content") else "0"

    # 颜色
    color_tag = soup.select_one("span.selected-color")
    color = color_tag.get_text(strip=True).replace("(", "").replace(")", "") if color_tag else "No Data"

    # 尺码（按钮文案）
    size_buttons = soup.select("div.size-wrapper button.size-button")
    size_map = {}
    for btn in size_buttons or []:
        size_text = btn.get_text(strip=True)
        if not size_text:
            continue
        # 简化：能点即认为“有货”（如果要更严谨，可检查 disabled/class）
        disabled = ("disabled" in (btn.get("class") or [])) or btn.has_attr("disabled")
        size_map[size_text] = "无货" if disabled else "有货"

    # 性别 / 主体材质
    product_gender = _extract_gender_from_html(html)
    product_material = _extract_material_from_features(features)

    info = {
        # ✅ 统一成“鲸芽模板”键名
        "Product Code": sku,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": product_gender,
        "Product Color": color,
        "Product Price": price,
        "Adjusted Price": price,          # 官网价=折后价（若后续抓到促销，再填不同）
        "Product Material": product_material,
        "Feature": features,
        "SizeMap": size_map,              # 简单供货；如你将来抓到 EAN/库存，可改写 SizeDetail
        "Source URL": url,
        "Site Name": "Barbour"            # 可选
        # 不传 Style Category → 由 txt_writer 内部 infer_style_category(desc) 自动兜底
    }
    return info

# -------- 主流程 --------

def fetch_and_write_txt():
    links_file = BARBOUR["LINKS_FILE"]
    txt_output_dir = Path(BARBOUR["TXT_DIR"])
    txt_output_dir.mkdir(parents=True, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"📄 共 {len(urls)} 个商品页面待解析...")

    for idx, url in enumerate(urls, 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            info = extract_product_info_from_html(resp.text, url)

            # 文件名优先用 SKU；没有就用安全化的标题兜底
            code_for_file = info.get("Product Code") or re.sub(r"[^A-Za-z0-9\-]+", "_", info.get("Product Name", "NoCode"))
            txt_path = txt_output_dir / f"{code_for_file}.txt"

            # ✅ 统一写入：走 camper/clarks_jingya 同一写入器
            format_txt(info, txt_path, brand="barbour")
            print(f"✅ [{idx}/{len(urls)}] 写入成功：{txt_path.name}")

        except Exception as e:
            print(f"❌ [{idx}/{len(urls)}] 失败：{url}，错误：{e}")

if __name__ == "__main__":
    fetch_and_write_txt()
