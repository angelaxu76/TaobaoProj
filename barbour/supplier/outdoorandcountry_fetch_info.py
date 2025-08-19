# -*- coding: utf-8 -*-
"""
Outdoor & Country | Barbour 商品抓取（统一写入 TXT：方案A）
依赖：
  pip install undetected-chromedriver bs4 lxml
项目依赖：
  from config import BARBOUR
  from txt_writer import format_txt
  from common_taobao.core.size_normalizer import build_size_fields_from_offers, infer_gender_for_barbour
  from common_taobao.core.category_utils import infer_style_category
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from config import BARBOUR
from common_taobao.txt_writer import format_txt
from common_taobao.core.size_normalizer import (
    build_size_fields_from_offers,
    infer_gender_for_barbour,
)
from common_taobao.core.category_utils import infer_style_category

# ========== 路径 ==========
BASE_DIR: Path = BARBOUR["BASE"]
PUBLICATION_DIR: Path = BASE_DIR / "publication"
LINK_FILE: Path = PUBLICATION_DIR / "product_links.txt"
TXT_DIR: Path = BARBOUR.get("TXT_DIR", BASE_DIR / "TXT")  # 兼容兜底

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ========== Selenium 基础 ==========
def make_driver(headless: bool = True):
    opts = uc.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    return uc.Chrome(options=opts)


def accept_cookies(driver, timeout: int = 8):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # Outdoor & Country 常见 cookie banner 按钮
        btns = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button|//a"))
        )
        for b in btns:
            txt = (b.text or "").strip().lower()
            if any(k in txt for k in ["accept", "agree", "got it", "allow", "i understand"]):
                try:
                    b.click()
                    time.sleep(0.3)
                    break
                except Exception:
                    pass
    except Exception:
        pass


# ========== 解析工具 ==========
def _load_soup(driver) -> BeautifulSoup:
    html = driver.page_source
    return BeautifulSoup(html, "lxml")


def _extract_text(soup: BeautifulSoup, selector: str) -> str:
    el = soup.select_one(selector)
    if not el:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def _extract_product_code_from_title_or_meta(soup: BeautifulSoup) -> Optional[str]:
    """
    Outdoor & Country 通常不用官方 color_code，但标题中常出现款式名，商品 code 需从页面数据结构获取。
    若 JS 中未含 code，这里兜底：找类似 "Barbour Beaufort Jacket" + 颜色，无法则返回 None。
    """
    title = _extract_text(soup, "h1") or _extract_text(soup, "title")
    # 常规：Barbour 会在图像URL或脚本块带 code；若拿不到，这里只返回 None，后续不强依赖。
    # 你也可以按你的规则通过 URL 参数或图片名来回推（此处不冒进）。
    m = re.search(r"\b([A-Z]{3}\d{4}[A-Z]{2}\d{2})\b", soup.text)  # 例如 MWX0340NY91
    if m:
        return m.group(1)
    return None


def _json_fixups(raw: str) -> str:
    """
    修复 Outdoor & Country 页里 JS 变量中常见的 JSON 问题：
    - HTML 片段里的引号、换行
    - 单引号包裹的键值
    - 末尾多逗号
    尽量“最小化修复”，避免误伤。
    """
    s = raw.strip()

    # 常见 HTML 实体
    s = s.replace("&quot;", '"').replace("&#34;", '"').replace("&amp;", "&")

    # 去掉可能的行尾逗号
    s = re.sub(r",\s*([\]}])", r"\1", s)

    # 将类似 key:'value' 修为 "key":"value"
    def _quote_keys_vals(match):
        key = match.group(1)
        val = match.group(2)
        return f'"{key}":"{val}"'

    s = re.sub(r"([A-Za-z0-9_]+)\s*:\s*'([^']*)'", _quote_keys_vals, s)

    # 将单引号包裹的字符串替换为双引号（不影响已在引号内的 JSON）
    # 注意：这里很容易过度修复，所以尽量在可控边界内做
    # 若仍失败，后续还有 try/except 容错
    return s


def _extract_js_var_block(soup: BeautifulSoup, var_name: str) -> Optional[str]:
    """
    在所有 <script> 中查找包含 var_name 的文本块，返回疑似 JSON 片段字符串
    例如：var stockInfo = {...}; 或 window.stockInfo = {...};
    """
    scripts = soup.find_all("script")
    pat = re.compile(rf"{var_name}\s*=\s*(\{{.*?\}}|\[.*?\])\s*[,;]", re.S)
    for sc in scripts:
        text = sc.string or sc.get_text() or ""
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def _safe_json_loads(raw: str) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(_json_fixups(raw))
    except Exception:
        return None


def _parse_colour_size_stock(soup: BeautifulSoup):
    """
    Outdoor & Country 的三大核心：
      - Colours: 颜色列表/ID映射
      - Sizes:   尺码列表/ID映射
      - stockInfo: { "<sizeId>-<colourId>": {...} }
    返回：(colours_dict, sizes_dict, stock_dict)
    """
    colours_raw = _extract_js_var_block(soup, "Colours")
    sizes_raw = _extract_js_var_block(soup, "Sizes")
    stock_raw = _extract_js_var_block(soup, "stockInfo")

    colours = _safe_json_loads(colours_raw) or {}
    sizes = _safe_json_loads(sizes_raw) or {}
    stock = _safe_json_loads(stock_raw) or {}

    return colours, sizes, stock


def _choose_active_colour_from_url(url: str, colours: dict) -> Optional[str]:
    """
    从 URL 的 ?c=xxx 或 path 中推断当前颜色文字/ID。
    找不到则返回 None（上层可默认取列表第一个）。
    """
    m = re.search(r"[?&]c=([^&]+)", url, re.I)
    if not m:
        return None
    c_param = m.group(1).lower()
    # 在 colours 结构里尝试匹配（结构多样，尽量宽松）
    # 允许直接比对 name 或 slug
    for cid, cinfo in (colours.items() if isinstance(colours, dict) else []):
        name = (cinfo.get("name") or "").lower()
        slug = (cinfo.get("url") or cinfo.get("slug") or "").lower()
        if c_param in {name, slug} or c_param in name or c_param in slug:
            return str(cid)
    return None


def _build_offer_list(colours: dict, sizes: dict, stock: dict, active_colour_id: Optional[str]) -> Tuple[str, List[Tuple[str, float, str, bool]]]:
    """
    组装 Offer 列表（(size_label, price, stock_text, can_order)）
    尽量选择 URL 指定的颜色；若无则选第一个颜色。
    返回：(color_name, offer_list)
    """
    if not isinstance(colours, dict) or not isinstance(sizes, dict) or not isinstance(stock, dict):
        return "", []

    # 选用颜色
    color_id = active_colour_id
    if not color_id:
        # 取第一个颜色 id
        if colours:
            color_id = str(next(iter(colours.keys())))
    color_name = ""
    if color_id and color_id in colours:
        color_name = colours[color_id].get("name") or colours[color_id].get("label") or ""

    # 组装每个尺码的库存
    offers: List[Tuple[str, float, str, bool]] = []
    for sid, sinfo in sizes.items():
        size_label = sinfo.get("name") or sinfo.get("label") or str(sid)
        key = f"{sid}-{color_id}"
        sitem = stock.get(key) or {}
        # 价格字段有时在 HTML/JS 的其他块里，这里尽量读取，没有就置 0
        price = 0.0
        for k in ("price", "salePrice", "sale", "now", "currentPrice"):
            v = sitem.get(k)
            try:
                if v is not None:
                    price = float(v)
                    break
            except Exception:
                pass

        # 库存判断：若有明确 availability 字段；否则看 stockLevelMessage / inStock 等
        stock_text = (sitem.get("stockLevelMessage") or sitem.get("availability") or "").strip()
        in_stock_flags = [
            sitem.get("inStock"),
            sitem.get("isInStock"),
            sitem.get("canOrder"),
            sitem.get("available"),
        ]
        can_order = any(bool(x) for x in in_stock_flags)

        # 如果没有显式布尔，但有文案，做一次粗判
        if not any(in_stock_flags) and stock_text:
            low = stock_text.lower()
            can_order = any(k in low for k in ["in stock", "available", "dispatch", "pre-order"])

        offers.append((size_label, price, stock_text, bool(can_order)))

    return color_name, offers


# ========== 页面解析主函数 ==========
def parse_outdoor_and_country(driver, url: str) -> Optional[Dict]:
    driver.get(url)
    time.sleep(1.6)
    accept_cookies(driver, timeout=8)
    time.sleep(0.5)

    soup = _load_soup(driver)

    title = _extract_text(soup, "h1") or _extract_text(soup, "title")
    description = _extract_text(soup, ".productView-description") or _extract_text(soup, '[data-tab-content="description"]')
    # Features（要点列表）
    features_block = soup.select(".productView-info .productView-info-name, .productView-info .productView-info-value")
    features = []
    if features_block:
        features_text = " ".join(x.get_text(" ", strip=True) for x in features_block)
        features.append(features_text)

    product_code = _extract_product_code_from_title_or_meta(soup)  # 可能抓不到，不强制
    colours, sizes, stock = _parse_colour_size_stock(soup)
    active_colour_id = _choose_active_colour_from_url(url, colours)
    color_name, offer_list = _build_offer_list(colours, sizes, stock, active_colour_id)

    # 站点名
    site_name = "Outdoor and Country"

    # 组装基础信息
    info: Dict = {
        "Product Name": title,
        "Product Description": description,
        "Product Gender": "",        # 稍后用共享模块修正
        "Product Color": color_name or "",
        "Style Category": "",        # 稍后判定
        "Feature": " | ".join(features) if features else "",
        "Source URL": url,
        "Site Name": site_name,
        "Offers": offer_list,        # 暂存，写入前转三字段
    }
    if product_code:
        info["Product Code"] = product_code
    info["Brand"] = "Barbour"

    # ====== 性别判定（优先 Code → 标题/描述 → 兜底）======
    gender = infer_gender_for_barbour(
        product_code=product_code,
        title=title,
        description=description,
        given_gender=info.get("Product Gender"),
    ) or "男款"
    info["Product Gender"] = gender

    # ====== 尺码三字段 ======
    size_map, size_detail, product_size = build_size_fields_from_offers(offer_list, gender)
    info["SizeMap"] = size_map
    info["SizeDetail"] = size_detail
    info["Product Size"] = product_size

    # ====== 风格类目 ======
    info["Style Category"] = infer_style_category(
        desc=description,
        product_name=title,
        product_code=product_code or "",
        brand="Barbour",
    )

    return info


# ========== 写入 & 批量 ==========
def write_one_product(info: Dict, code_hint: Optional[str] = None):
    """
    code_hint：当页面无法提取到 Product Code 时，用于写文件名的兜底。
    """
    code = info.get("Product Code") or code_hint
    if not code:
        # 没有 code 就用标题降级成安全文件名
        safe = re.sub(r"[^\w\-]+", "_", (info.get("Product Name") or "barbour_item"))
        code = safe[:50]

    TXT_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = TXT_DIR / f"{code}.txt"
    format_txt(info, txt_path, brand="Barbour")
    print(f"✅ 写入: {txt_path}")


def fetch_one(url: str, driver=None):
    own_driver = False
    if driver is None:
        driver = make_driver(headless=True)
        own_driver = True
    try:
        info = parse_outdoor_and_country(driver, url)
        if info:
            # 尝试从 URL 猜测 code（可选）
            code_hint = None
            m = re.search(r"/([A-Za-z0-9]{3}\d{4}[A-Za-z]{2}\d{2})", url)
            if m:
                code_hint = m.group(1)
            write_one_product(info, code_hint=code_hint)
        else:
            print(f"⚠️ 解析失败: {url}")
    finally:
        if own_driver:
            driver.quit()


def main():
    import sys
    urls: List[str] = []
    if len(sys.argv) > 1:
        urls = sys.argv[1:]
    else:
        if LINK_FILE.exists():
            urls = [u.strip() for u in LINK_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]

    if not urls:
        print("⚠️ 未发现待抓取链接。可在命令行传入 URL，或在 publication/product_links.txt 填入链接。")
        return

    driver = make_driver(headless=True)
    try:
        for i, url in enumerate(urls, 1):
            print(f"🌐 [{i}/{len(urls)}] 抓取: {url}")
            fetch_one(url, driver=driver)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
