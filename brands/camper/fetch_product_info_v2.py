# camper_fetch_product_info_fast.py
import re
import json
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from config import CAMPER, SIZE_RANGE_CONFIG
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category

PRODUCT_URLS_FILE = Path(CAMPER["LINKS_FILE"])
SAVE_PATH = Path(CAMPER["TXT_DIR"])
SAVE_PATH.mkdir(parents=True, exist_ok=True)

# requests 并发推荐 8~16；如果你网络不稳可以先 8
MAX_WORKERS = 12

# ---------------------------
# 工具函数
# ---------------------------

def infer_gender_from_url(url: str) -> str:
    u = url.lower()
    if "/women/" in u:
        return "女款"
    if "/men/" in u:
        return "男款"
    if "/kids/" in u or "/children/" in u:
        return "童款"
    return "未知"


def _num_from_any(x) -> float:
    """把 '£145'、'145.00'、145 转成 float；失败返回 0.0"""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return 0.0
    # 去掉货币符号、空格等
    s = s.replace(",", "")
    m = re.search(r"(\d+(\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0


def extract_prices(product_sheet: dict) -> tuple[float, float]:
    """
    输出 (original_price, discount_price)
    兼容不同字段结构，尽量保证折扣价/原价正确。
    """
    prices = product_sheet.get("prices") or {}

    # 常见：{"previous": 170, "current": 119}
    prev = _num_from_any(prices.get("previous"))
    curr = _num_from_any(prices.get("current"))

    if curr or prev:
        # 如果只有 current，没有 previous：把 current 当成交价，原价=成交价
        if curr and not prev:
            return curr, curr
        # 如果只有 previous，没有 current：把 previous 当作原价，成交价=原价
        if prev and not curr:
            return prev, prev
        return prev, curr

    # 兼容：可能是 {"price": {"value":..}, "sale": {"value":..}} 或类似命名
    candidates = [
        ("was", "now"),
        ("original", "current"),
        ("regular", "current"),
        ("price", "sale"),
        ("list", "sale"),
        ("rrp", "sale"),
    ]
    for a, b in candidates:
        a_obj = prices.get(a)
        b_obj = prices.get(b)
        a_val = _num_from_any(a_obj.get("value") if isinstance(a_obj, dict) else a_obj)
        b_val = _num_from_any(b_obj.get("value") if isinstance(b_obj, dict) else b_obj)
        if a_val or b_val:
            if b_val and not a_val:
                return b_val, b_val
            if a_val and not b_val:
                return a_val, a_val
            return a_val, b_val

    # 兜底：有些站点把价格塞在别处（比如 product_sheet["price"]）
    for key in ["price", "currentPrice", "salePrice", "finalPrice"]:
        v = _num_from_any(product_sheet.get(key))
        if v:
            return v, v

    return 0.0, 0.0


def extract_features_and_upper(product_sheet: dict) -> tuple[str, str]:
    features_raw = product_sheet.get("features") or []
    feature_texts = []
    upper_material = "No Data"

    for f in features_raw:
        if not isinstance(f, dict):
            continue

        # Feature 文本
        value_html = f.get("value") or ""
        clean_text = BeautifulSoup(value_html, "html.parser").get_text(strip=True)
        if clean_text:
            feature_texts.append(clean_text)

        # Upper 材质
        name = (f.get("name") or "").lower()
        if upper_material == "No Data" and "upper" in name:
            upper_material = clean_text or "No Data"

    feature_str = " | ".join(feature_texts) if feature_texts else "No Data"
    return feature_str, upper_material


def extract_sizes(product_sheet: dict) -> tuple[dict, dict]:
    size_map = {}
    size_detail = {}

    for size in (product_sheet.get("sizes") or []):
        if not isinstance(size, dict):
            continue

        value = (size.get("value") or "").strip()
        if not value:
            continue

        available = bool(size.get("available", False))
        quantity = int(size.get("quantity", 0) or 0)

        # ean 可能为空
        ean = size.get("ean") or ""

        size_map[value] = "有货" if available else "无货"
        size_detail[value] = {
            "stock_count": quantity,
            "ean": ean,
        }

    return size_map, size_detail


# thread-local requests Session（requests.Session 不是严格线程安全，别全局共享一个）
thread_local = threading.local()

def get_http_session() -> requests.Session:
    if not hasattr(thread_local, "sess") or thread_local.sess is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Connection": "keep-alive",
        })
        thread_local.sess = s
    return thread_local.sess


def fetch_next_data(url: str, timeout=20, retry=2) -> tuple[str, dict] | tuple[str, None]:
    """
    返回 (title, product_sheet)；失败返回 (title/空, None)
    """
    sess = get_http_session()
    last_err = None

    for i in range(retry + 1):
        try:
            r = sess.get(url, timeout=timeout)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            title_tag = soup.find("title")
            title_text = title_tag.get_text(strip=True) if title_tag else ""

            script_tag = soup.select_one("script#__NEXT_DATA__")
            if not script_tag or not script_tag.string:
                return title_text, None

            data = json.loads(script_tag.string)

            product_sheet = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("productSheet")
            )
            return title_text, product_sheet

        except Exception as e:
            last_err = e
            # 简单退避
            time.sleep(0.6 * (i + 1))

    return "", None


def process_product_url(url: str) -> tuple[bool, str, str]:
    try:
        print(f"\n🔍 正在访问: {url}")
        title_text, product_sheet = fetch_next_data(url)

        if not product_sheet:
            return False, url, "未获取到 productSheet（可能页面结构变化/跳转）"

        # title 去掉后缀
        product_title = re.sub(r"\s*[-–—].*", "", (title_text or "").strip()) or "Unknown Title"

        product_code = product_sheet.get("code", "Unknown_Code")
        description = product_sheet.get("description", "") or ""

        original_price, discount_price = extract_prices(product_sheet)

        color_data = product_sheet.get("color", "")
        color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

        feature_str, upper_material = extract_features_and_upper(product_sheet)
        size_map, size_detail = extract_sizes(product_sheet)

        gender = infer_gender_from_url(url)

        # 尺码补全（保留你的逻辑）
        standard_sizes = SIZE_RANGE_CONFIG.get("camper", {}).get(gender, [])
        if standard_sizes:
            missing_sizes = [s for s in standard_sizes if s not in size_detail]
            for s in missing_sizes:
                size_map[s] = "无货"
                size_detail[s] = {"stock_count": 0, "ean": ""}
            if missing_sizes:
                print(f"⚠️ {product_code} 补全尺码: {', '.join(missing_sizes)}")

        style_category = infer_style_category(description)

        info = {
            "Product Code": product_code,
            "Product Name": product_title,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,

            # ✅ 价格：原价/折扣价（最新版正确逻辑的稳健版）
            "Product Price": str(original_price),
            "Adjusted Price": str(discount_price),

            "Product Material": upper_material,
            "Style Category": style_category,
            "Feature": feature_str,

            "SizeMap": size_map,
            "SizeDetail": size_detail,

            "Source URL": url,
        }

        filepath = SAVE_PATH / f"{product_code}.txt"
        format_txt(info, filepath, brand="camper")
        print(f"✅ 完成 TXT: {filepath.name} | 原价={original_price} 折扣价={discount_price}")
        return True, url, ""

    except Exception as e:
        return False, url, str(e)


from pathlib import Path
from typing import Optional, List

def camper_fetch_product_info(
    links_file: Optional[str] = None,
    urls: Optional[List[str]] = None,
    max_workers: int = MAX_WORKERS
):
    # ✅ 防呆：避免把路径字符串误当 max_workers
    if not isinstance(max_workers, int):
        raise TypeError(f"max_workers must be int, got {type(max_workers)}: {max_workers!r}")

    # 1) 优先用 urls（来自 DB）
    if urls is not None:
        url_list = [u.strip() for u in urls if u and u.strip()]
        source = "urls(list)"
    else:
        # 2) 其次用 links_file（比如 missing_product_links.txt）
        lf = Path(links_file) if links_file else PRODUCT_URLS_FILE
        with open(lf, "r", encoding="utf-8") as f:
            url_list = [line.strip() for line in f if line.strip()]
        source = str(lf)

    print(f"📄 使用链接来源: {source} | 共 {len(url_list)} 条 | MAX_WORKERS={max_workers}")

    ok_cnt = 0
    fail_cnt = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_product_url, u) for u in url_list]
        for fut in as_completed(futures):
            ok, url, msg = fut.result()
            if ok:
                ok_cnt += 1
            else:
                fail_cnt += 1
                print(f"❌ 失败: {url} | {msg}")

    print(f"\n✅ 完成：成功 {ok_cnt}，失败 {fail_cnt}，输出目录：{SAVE_PATH}")



if __name__ == "__main__":
    camper_fetch_product_info()
