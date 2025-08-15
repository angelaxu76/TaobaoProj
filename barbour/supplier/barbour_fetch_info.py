import os
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from config import BARBOUR
from barbour.barbouir_write_offer_txt import write_barbour_product_txt

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
}

# ------ 工具函数 ------

def _safe_json_loads(text: str):
    """尝试将字符串解析为 JSON；失败则返回 None。"""
    try:
        return json.loads(text)
    except Exception:
        return None

def _extract_gender_from_html(html: str) -> str:
    """
    从 gtmAnalytics 的 items[0].item_category 提取性别：
      womens -> 女款, mens -> 男款, kids -> 童款
    """
    # 1) 先粗暴正则兜底（最鲁棒、对 script 内部结构变动不敏感）
    m = re.search(r'"item_category"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    gender_raw = m.group(1).strip().lower() if m else ""

    # 2) 若正则没命中，再尝试解析可能的 JSON 片段（更语义化）
    if not gender_raw:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            if not script.string:
                continue
            s = script.string.strip()
            if "gtmAnalytics" in s and "items" in s and "item_category" in s:
                # 提取 "gtmAnalytics": {...} 里的 JSON 体（尽量小心匹配）
                # 简化做法：直接正则拿 item_category 值
                m2 = re.search(r'"item_category"\s*:\s*"([^"]+)"', s, re.IGNORECASE)
                if m2:
                    gender_raw = m2.group(1).strip().lower()
                    break

    mapping = {
        "womens": "女款",
        "women": "女款",
        "ladies": "女款",
        "mens": "男款",
        "men": "男款",
        "kids": "童款",
        "child": "童款",
        "children": "童款",
        "unisex": "通用"
    }
    return mapping.get(gender_raw, "未知")

def _extract_material_from_features(features_text: str) -> str:
    """
    从 features 文本中提取“主体材质”。
    规则：
      1) 先找 Outer / Shell / Fabric / Material 等前缀后面的配方；
      2) 否则在整串里找第一个 “xx% 材质”；
      3) 过滤掉 Lining / Trim / Collar / Sleeve / Cuff 等非主体字段；
      4) 最终返回诸如 “100% Cotton” 或“65% Polyester / 35% Cotton”。
    """
    if not features_text or features_text == "No Data":
        return "No Data"

    # 统一分隔，避免 HTML 中的 <br>、换行等
    text = features_text.replace("\n", " ").replace("\r", " ")
    parts = re.split(r"\s*\|\s*|,\s+|;\s+|/+\s*", text)  # 以 | 或逗号/分号/斜线拆分，后续会重组
    parts = [p.strip() for p in parts if p and p.strip()]

    # 屏蔽非主体字段关键词
    exclude_prefixes = ("lining", "trim", "collar", "sleeve", "cuff", "hood", "pocket")
    # 主体字段前缀关键词
    primary_prefixes = ("outer", "shell", "face", "fabric", "material", "main", "outer fabric", "outer shell")

    # 1) 先尝试：从显式“主体关键词”中提取百分比材质
    for p in parts:
        low = p.lower()
        if any(low.startswith(pref) for pref in primary_prefixes):
            # 例： "Outer: 100% Polyamide" / "Fabric: 65% Polyester 35% Cotton"
            # 先剥离前缀及冒号
            candidate = re.sub(r"^[A-Za-z ]+\s*:\s*", "", p).strip()
            # 匹配一个或多个“百分比+材质”
            mats = re.findall(r"\b\d{1,3}%\s+[A-Za-z][A-Za-z \-]*", candidate)
            if mats:
                # 有时可能是 "65% Polyester 35% Cotton" 无分隔，尝试拆两段
                # 追加第二段
                joined = " / ".join(mats)
                return joined

    # 2) 再尝试：全局找第一处 “xx% 材质”，但要过滤非主体字段
    for p in parts:
        low = p.lower()
        if any(low.startswith(pref) for pref in exclude_prefixes):
            continue
        mats = re.findall(r"\b\d{1,3}%\s+[A-Za-z][A-Za-z \-]*", p)
        if mats:
            return " / ".join(mats)

    # 3) 兜底：全量扫描（不排除前缀），取第一组
    mats_all = re.findall(r"\b\d{1,3}%\s+[A-Za-z][A-Za-z \-]*", text)
    if mats_all:
        return " / ".join(mats_all[:2])  # 最多返回前两段，避免过长

    # 4) 再兜底：如果出现 "100% Cotton (Waxed)" 这类，去掉括号只取核心材质词
    m = re.search(r"\b\d{1,3}%\s+([A-Za-z][A-Za-z \-]*)\b", text)
    if m:
        return f"{text[m.start():m.end()]}"  # 已经是“xx% 材质”的样式

    return "No Data"

# ------ 解析核心 ------

def extract_product_info_from_html(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    # 名称
    name = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _safe_json_loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product" and "name" in data:
                name = data["name"].strip()
                break
        except:
            continue

    # SKU
    sku = "No Data"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _safe_json_loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product" and "sku" in data:
                sku = str(data["sku"]).strip()
                break
        except:
            continue

    # 描述
    desc_tag = soup.find("div", {"id": "collapsible-description-1"})
    description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else "No Data"
    # 有些页面会把 “SKU: XXX” 混在描述中，做个清理
    if sku and sku != "No Data":
        description = description.replace(f"SKU: {sku}", "").strip()

    # Feature（含 保养/材质）
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

    # 性别（新增）
    product_gender = _extract_gender_from_html(html)

    # 主体材质（新增）
    product_material = _extract_material_from_features(features)

    info = {
        "Product Code": sku,
        "Product Name": name,
        "Product Description": description if description else "No Data",
        "Product Gender": product_gender,                # ✅ 新增
        "Product Color": color,
        "Product Price": price,
        "Adjusted Price": price,
        "Product Material": product_material,            # ✅ 新增
        "Feature": features,
        "SizeMap": size_map,
        "Source URL": url,
        "Site Name": "Barbour"
    }
    return info

# ------ 主流程 ------

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

            # 文件名用 SKU；若 SKU 缺失则用安全化的名称兜底
            code_for_file = info.get("Product Code") or re.sub(r"[^A-Za-z0-9\-]+", "_", info.get("Product Name", "NoCode"))
            txt_path = Path(txt_output_dir) / f"{code_for_file}.txt"

            write_barbour_product_txt(info, txt_path, brand="barbour")
            print(f"✅ [{idx}/{len(urls)}] 写入成功：{txt_path.name}")
        except Exception as e:
            print(f"❌ [{idx}/{len(urls)}] 失败：{url}，错误：{e}")

if __name__ == "__main__":
    fetch_and_write_txt()
