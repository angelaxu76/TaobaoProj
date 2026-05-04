"""
GEOX 商品信息快速抓取（requests + 多线程）
适用场景：折扣公开、无需登录（日常模式）

会员专属打折模式请用 fetch_product_info_jingya.py（Selenium + Chrome Profile）
"""
import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import SIZE_RANGE_CONFIG, GEOX, DEFAULT_STOCK_COUNT
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category

# ===================== 配置 =====================
PRODUCT_LINK_FILE = GEOX["BASE"] / "publication" / "product_links.txt"
TXT_OUTPUT_DIR = GEOX["TXT_DIR"]
BRAND = "geox"
MAX_THREADS = 8      # requests 无浏览器开销，可跑更多线程；如被限速降到 4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ===================== 解析工具 =====================
def supplement_geox_sizes(size_stock: Dict[str, str], gender: str) -> Dict[str, str]:
    standard_sizes = SIZE_RANGE_CONFIG.get("geox", {}).get(gender, [])
    for size in standard_sizes:
        if size not in size_stock:
            size_stock[size] = "0"
    return size_stock


def detect_gender_by_code(code: str) -> str:
    if not code:
        return "未知"
    code = code.strip().upper()
    if code.startswith("D"):
        return "女款"
    if code.startswith("U"):
        return "男款"
    if code.startswith("J"):
        return "童款"
    return "未知"


def _safe_select_value(soup, selector: str):
    """排除商品推荐/轮播区域，只取 PDP 主区域的节点。"""
    for node in soup.select(selector):
        if node.find_parent(class_="product-tile") or node.find_parent(
            class_="product-carousel-tile"
        ):
            continue
        return node
    return None


def extract_max_price(val) -> str:
    if not val:
        return "No Data"
    s = str(val).strip()
    if "-" in s:
        try:
            parts = [float(p.strip()) for p in s.split("-") if p.strip()]
            return f"{max(parts):.2f}"
        except Exception:
            return s
    return s


def derive_code_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        from pathlib import PurePosixPath
        base = PurePosixPath(path).name.split("?", 1)[0]
        token = base.rsplit("-", 1)[-1]
        code = token.split(".", 1)[0].upper()
        if len(code) < 6 or not any(ch.isdigit() for ch in code):
            m = re.search(r"([A-Za-z0-9]{6,})\.html$", base)
            if m:
                code = m.group(1).upper()
        return code
    except Exception:
        return PurePosixPath(urlparse(url).path).stem.upper()


# ===================== 核心抓取 =====================
def parse_product(html: str, url: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    code_tag = soup.select_one("span.product-id")
    code = code_tag.get_text(strip=True) if code_tag else derive_code_from_url(url)

    name_tag = soup.select_one("div.sticky-image img")
    name = (
        name_tag["alt"].strip()
        if name_tag and name_tag.has_attr("alt")
        else "No Data"
    )

    price_tag = _safe_select_value(soup, "span.product-price span.value")
    discount_tag = _safe_select_value(soup, "span.sales.discount span.value")

    full_price_raw = (
        (price_tag.get("content") or price_tag.get_text(strip=True).replace("£", "")).strip()
        if price_tag else ""
    )
    discount_price_raw = (
        (discount_tag.get("content") or discount_tag.get_text(strip=True).replace("£", "")).strip()
        if discount_tag else ""
    )

    original_price = extract_max_price(full_price_raw) or "No Data"

    discount_price = extract_max_price(discount_price_raw) if discount_price_raw else ""
    try:
        op = float(original_price) if original_price not in ("", "No Data") else None
        dp = float(discount_price) if discount_price not in ("", "No Data") else None
        if dp is None or op is None or dp >= op or dp < op * 0.3:
            discount_price = original_price
    except Exception:
        discount_price = original_price

    color_block = soup.select_one("div.sticky-color")
    color = (
        color_block.get_text(strip=True).replace("Color:", "").strip()
        if color_block else "No Data"
    )

    materials_block = soup.select_one("div.materials-container")
    material_text = (
        materials_block.get_text(" ", strip=True) if materials_block else "No Data"
    )

    desc_block = soup.select_one("div.product-description div.value")
    description = desc_block.get_text(strip=True) if desc_block else "No Data"

    gender = detect_gender_by_code(code)

    size_blocks = soup.select("div.size-value")
    size_stock: Dict[str, str] = {}
    for sb in size_blocks:
        size = sb.get("data-attr-value") or sb.get("prodsize") or sb.get("aria-label")
        size = size.strip().replace(",", ".") if size else "Unknown"
        available = "1" if "disabled" not in sb.get("class", []) else "0"
        size_stock[size] = available

    size_stock = supplement_geox_sizes(size_stock, gender)

    size_map: Dict[str, str] = {}
    size_detail: Dict[str, Dict] = {}
    for eu, flag in size_stock.items():
        has = str(flag) == "1"
        size_map[eu] = "有货" if has else "无货"
        size_detail[eu] = {"stock_count": DEFAULT_STOCK_COUNT if has else 0, "ean": "0000000000000"}

    style_category = infer_style_category(f"{name} {description}")

    feature_block = soup.select_one("div.bestFor-container")
    if feature_block:
        items = [li.get_text(strip=True) for li in feature_block.select("ul li")]
        feature = " | ".join(items) if items else "No Data"
    else:
        feature = "No Data"

    return {
        "Product Code": code,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": original_price,
        "Adjusted Price": discount_price,
        "Product Material": material_text,
        "Style Category": style_category,
        "Feature": feature,
        "SizeMap": size_map,
        "SizeDetail": size_detail,
        "Source URL": url,
    }


def fetch_one(session: requests.Session, idx: int, total: int, url: str) -> Tuple[bool, str]:
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        info = parse_product(r.text, url)
        if not info:
            print(f"[{idx}/{total}] ⚠️ 解析失败: {url}")
            return False, url

        txt_path = TXT_OUTPUT_DIR / f"{info['Product Code']}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        format_txt(info, txt_path, brand=BRAND)
        print(f"[{idx}/{total}] ✅ {info['Product Code']}")
        return True, url

    except Exception as e:
        print(f"[{idx}/{total}] ❌ {url} → {e}")
        return False, url


# ===================== 主入口 =====================
def fetch_all_product_info(links_file=None, max_workers: int = MAX_THREADS):
    """
    GEOX 快速抓取入口（requests + 多线程，无需浏览器）。
    接口与 fetch_product_info_jingya.py 完全兼容。

    :param links_file: 可选，自定义 product_links.txt 路径。
    :param max_workers: 线程数，默认 8；被限速时调低。
    """
    links_path = Path(links_file) if links_file else PRODUCT_LINK_FILE
    if not links_path.exists():
        print(f"❌ 缺少链接文件: {links_path}")
        return

    with open(links_path, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip()]

    if not urls:
        print(f"⚠️ 链接列表为空: {links_path}")
        return

    total = len(urls)
    print(f"📦 本次需要抓取 GEOX 商品数量: {total}，线程数: {max_workers}")
    t0 = time.time()
    success = fail = 0

    session = requests.Session()
    # 先访问首页，拿到 cookies（避免部分反爬检测）
    try:
        session.get("https://www.geox.com/en-GB/", headers=HEADERS, timeout=10)
    except Exception:
        pass

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_one, session, idx, total, url): url
            for idx, url in enumerate(urls, 1)
        }
        for fut in as_completed(futures):
            ok, _ = fut.result()
            if ok:
                success += 1
            else:
                fail += 1

    dt = time.time() - t0
    print(
        f"\n✅ GEOX 抓取完成：成功 {success} 条，失败 {fail} 条，"
        f"耗时约 {dt/60:.1f} 分钟"
    )


if __name__ == "__main__":
    fetch_all_product_info()
