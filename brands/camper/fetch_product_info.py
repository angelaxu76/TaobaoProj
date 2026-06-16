# -*- coding: utf-8 -*-
# fetch_product_info_v5.py
# V2 (requests, 无 Chrome) + voucherPrices 折扣价提取
import gc
import re
import json
import time
import threading
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from config import CAMPER, SIZE_RANGE_CONFIG
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category

PRODUCT_URLS_FILE = Path(CAMPER["LINKS_FILE"])
SAVE_PATH = Path(CAMPER["TXT_DIR"])
SAVE_PATH.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 8  # requests 并发，可根据网络调整


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


def _num(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^\d.]", "", str(x).strip())
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


# ---------------------------
# 价格提取（两层）
# ---------------------------

def extract_prices(product_sheet: dict) -> tuple[float, float, str]:
    """
    1. voucherPrices（最直接的折扣信号）
       取所有 voucher 里折扣最大的那个
    2. prices.previous / prices.current（普通折扣）
    3. 兜底：只用 current 作为原价
    """
    # --- 1. voucherPrices ---
    voucher_prices = product_sheet.get("voucherPrices") or {}
    best_sale = float("inf")
    best_orig = 0.0
    best_key = ""
    for key, vp in voucher_prices.items():
        if not isinstance(vp, dict):
            continue
        curr = _num(vp.get("current"))
        prev = _num(vp.get("previous"))
        if curr > 0 and prev > 0 and prev > curr and curr < best_sale:
            best_sale = round(curr, 2)
            best_orig = round(prev, 2)
            best_key = key
    if best_key:
        return best_orig, best_sale, f"voucher_{best_key}"

    # --- 2. prices.previous / current ---
    prices = product_sheet.get("prices") or {}
    prev = _num(prices.get("previous"))
    curr = _num(prices.get("current"))
    if prev > 0 and curr > 0 and prev != curr:
        orig, sale = (prev, curr) if prev > curr else (curr, prev)
        return round(orig, 2), round(sale, 2), "prices_prev_curr"
    if curr > 0:
        return round(curr, 2), round(curr, 2), "prices_curr_only"
    if prev > 0:
        return round(prev, 2), round(prev, 2), "prices_prev_only"

    # --- 3. 其他兜底字段 ---
    for key in ["price", "currentPrice", "salePrice", "finalPrice"]:
        v = _num(product_sheet.get(key))
        if v:
            return round(v, 2), round(v, 2), f"fallback_{key}"

    return 0.0, 0.0, "no_price"


# ---------------------------
# 特征 & 材质 & 尺码（与 V2/V4 相同）
# ---------------------------

def extract_features_and_upper(product_sheet: dict) -> tuple[str, str]:
    features_raw = product_sheet.get("features") or []
    feature_texts = []
    upper_material = "No Data"
    cur_label = None
    cur_parts = []

    for f in features_raw:
        if not isinstance(f, dict):
            continue
        name_html = f.get("name") or ""
        value_html = f.get("value") or ""
        name_clean = BeautifulSoup(name_html, "html.parser").get_text(strip=True)
        value_clean = BeautifulSoup(value_html, "html.parser").get_text(strip=True)

        if re.search(r"<b>|<strong>", name_html, re.I):
            if cur_label is not None:
                combined = " ".join(p for p in cur_parts if p)
                feature_texts.append(f"{cur_label}: {combined}" if combined else cur_label)
            cur_label = name_clean
            cur_parts = [value_clean] if value_clean else []
            if upper_material == "No Data" and "upper" in name_clean.lower():
                upper_material = value_clean or "No Data"
        else:
            if name_clean:
                cur_parts.append(name_clean)
            if value_clean:
                cur_parts.append(value_clean)

    if cur_label is not None:
        combined = " ".join(p for p in cur_parts if p)
        feature_texts.append(f"{cur_label}: {combined}" if combined else cur_label)

    return " | ".join(feature_texts) if feature_texts else "No Data", upper_material


def extract_sizes(product_sheet: dict) -> tuple[dict, dict]:
    size_map = {}
    size_detail = {}
    for size in (product_sheet.get("sizes") or []):
        if not isinstance(size, dict):
            continue
        value = (size.get("value") or "").strip()
        if not value:
            continue
        size_map[value] = "有货" if bool(size.get("available", False)) else "无货"
        size_detail[value] = {
            "stock_count": int(size.get("quantity", 0) or 0),
            "ean": size.get("ean") or "",
        }
    return size_map, size_detail


# ---------------------------
# HTTP 抓取（thread-local Session）
# ---------------------------

_thread_local = threading.local()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "sess") or _thread_local.sess is None:
        s = requests.Session()
        s.headers.update(_HEADERS)
        _thread_local.sess = s
    return _thread_local.sess


def _fetch_product_sheet(url: str, timeout: int = 20, retry: int = 2) -> tuple[str, dict | None]:
    """返回 (title, product_sheet)；失败返回 ('', None)"""
    sess = _get_session()
    last_err = None
    for attempt in range(retry + 1):
        try:
            r = sess.get(url, timeout=timeout)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            script_tag = soup.select_one("script#__NEXT_DATA__")
            if not script_tag or not script_tag.string:
                del soup
                return title, None

            data = json.loads(script_tag.string)
            product_sheet = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("productSheet")
            )
            del soup, data, script_tag
            gc.collect()
            return title, product_sheet

        except Exception as e:
            last_err = e
            time.sleep(0.8 * (attempt + 1))

    return "", None


# ---------------------------
# 单 URL 处理
# ---------------------------

def process_product_url(url: str) -> tuple[bool, str, str]:
    try:
        print(f"\n🔍 正在访问: {url}")
        title_text, product_sheet = _fetch_product_sheet(url)

        if not product_sheet:
            return False, url, "未获取到 productSheet（页面结构变化或被拦截）"

        product_title = re.sub(r"\s*[-–—].*", "", (title_text or "").strip()) or "Unknown Title"
        product_code = product_sheet.get("code", "Unknown_Code")
        description = product_sheet.get("description", "") or ""

        original_price, discount_price, price_src = extract_prices(product_sheet)

        color_data = product_sheet.get("color", "")
        color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

        feature_str, upper_material = extract_features_and_upper(product_sheet)
        size_map, size_detail = extract_sizes(product_sheet)

        gender = infer_gender_from_url(url)
        standard_sizes = SIZE_RANGE_CONFIG.get("camper", {}).get(gender, [])
        if standard_sizes:
            missing = [s for s in standard_sizes if s not in size_detail]
            for s in missing:
                size_map[s] = "无货"
                size_detail[s] = {"stock_count": 0, "ean": ""}
            if missing:
                print(f"⚠️ {product_code} 补全尺码: {', '.join(missing)}")

        style_category = infer_style_category(description)

        info = {
            "Product Code": product_code,
            "Product Name": product_title,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": color,
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
        del product_sheet, info
        gc.collect()

        disc_label = "no_discount" if original_price == discount_price else "DISCOUNT"
        print(f"✅ 完成 TXT: {filepath.name}  [{disc_label}] src={price_src}  P={original_price:.2f}, D={discount_price:.2f}")
        return True, url, ""

    except Exception as e:
        return False, url, str(e)


# ---------------------------
# 入口函数（与 V2/V4 签名兼容）
# ---------------------------

def camper_fetch_product_info(
    links_file: Optional[str] = None,
    urls: Optional[List[str]] = None,
    max_workers: int = MAX_WORKERS,
    product_urls_file: Optional[str] = None,
):
    if not isinstance(max_workers, int) or max_workers < 1:
        raise TypeError(f"max_workers must be a positive int, got {max_workers!r}")

    if urls is not None:
        url_list = [u.strip() for u in urls if u and u.strip()]
        source = "urls(list)"
    else:
        lf = links_file or product_urls_file or str(PRODUCT_URLS_FILE)
        with open(lf, "r", encoding="utf-8") as f:
            url_list = [line.strip() for line in f if line.strip()]
        source = lf

    print(f"📄 使用链接来源: {source} | 共 {len(url_list)} 条 | MAX_WORKERS={max_workers}")

    ok_cnt = 0
    failed = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(process_product_url, u) for u in url_list]
        for fut in as_completed(futures):
            ok, url, err = fut.result()
            if ok:
                ok_cnt += 1
            else:
                print(f"❌ 失败: {url} | {err}")
                failed.append(url)

    if failed:
        fail_path = SAVE_PATH.parent / "failed_urls_v5.txt"
        fail_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"⚠️ 失败链接已输出: {fail_path}")

    print(f"\n✅ 全部完成，成功 {ok_cnt}，失败 {len(failed)}")


if __name__ == "__main__":
    camper_fetch_product_info()
