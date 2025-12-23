# fetch_product_info_v3.py  (PUBLIC + MULTI-THREAD)
# ✅ 保持不变：
# - camper_fetch_product_info(product_urls_file: Optional[str] = None, login_wait_seconds: int = LOGIN_WAIT_SECONDS)
# - URL list 读取逻辑
# - process_product_url_with_driver 页面获取/解析逻辑
# ✅ 只改动：
# - Chrome/driver 逻辑：不登录、不共享cookie，每线程独立driver
# - 多线程调度逻辑：ThreadPoolExecutor

import os
import re
import time
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CAMPER, SIZE_RANGE_CONFIG
from common_taobao.ingest.txt_writer import format_txt
from common_taobao.core.category_utils import infer_style_category
from common_taobao.core.selenium_utils import get_driver

# =========================
# Config
# =========================
HOME_URL = "https://www.camper.com/en_GB"

PRODUCT_URLS_FILE = CAMPER["LINKS_FILE"]
SAVE_PATH = CAMPER["TXT_DIR"]

# ✅ v3-public-mt：多线程
MAX_WORKERS = 4  # 建议 3~5，先用 4，稳定后再加

# 保持参数兼容（虽然 public 版不登录，但函数签名不变）
LOGIN_WAIT_SECONDS = 30

DEBUG_ENABLED = False  # True 开启页面 dump
DEBUG_DIR = str(Path(SAVE_PATH).resolve().parent / "debug_camper")
Path(DEBUG_DIR).mkdir(parents=True, exist_ok=True)

os.makedirs(SAVE_PATH, exist_ok=True)

# =========================
# Utils
# =========================
def _safe_float(v) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def infer_gender_from_url(url: str) -> str:
    u = url.lower()
    if "/women/" in u:
        return "女款"
    if "/men/" in u:
        return "男款"
    if "/kids/" in u or "/children/" in u:
        return "童款"
    return "未知"


def is_driver_connection_error(e: Exception) -> bool:
    msg = str(e)
    return (
        "WinError 10061" in msg
        or "Max retries exceeded" in msg
        or "NewConnectionError" in msg
        or "Failed to establish a new connection" in msg
        or ("localhost" in msg and "/session/" in msg)
    )


def dump_debug_page(driver, name: str):
    if not DEBUG_ENABLED:
        return

    safe = re.sub(r"[^\w\-\.]+", "_", name)[:120]
    d = Path(DEBUG_DIR) / safe
    d.mkdir(parents=True, exist_ok=True)

    # HTML
    with open(d / "page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    # NEXT_DATA
    soup = BeautifulSoup(driver.page_source, "html.parser")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if tag and tag.string:
        try:
            j = json.loads(tag.string)
            with open(d / "next_data.json", "w", encoding="utf-8") as f:
                json.dump(j, f, indent=2, ensure_ascii=False)
        except Exception as ex:
            with open(d / "next_data_error.txt", "w", encoding="utf-8") as f:
                f.write(str(ex))

    # cookies
    try:
        with open(d / "cookies.json", "w", encoding="utf-8") as f:
            json.dump(driver.get_cookies(), f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # meta
    try:
        lower = driver.page_source.lower()
        meta = [
            f"URL: {driver.current_url}",
            f"Cookies count: {len(driver.get_cookies())}",
            f"voucherPrices: {'FOUND' if (tag and tag.string and 'voucherPrices' in tag.string) else 'NOT_FOUND'}",
            "login_hint: " + ("maybe_logged_in" if ("logout" in lower or "my account" in lower) else "unknown"),
        ]
        with open(d / "meta.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(meta))
    except Exception:
        pass


def pick_prices_from_product_sheet(product_sheet: dict) -> Tuple[float, float, str]:
    """
    v3：保持原逻辑不变（你要求页面逻辑不改）
    - public 模式下通常没有 voucherPrices，会自动落到 public/no_discount 分支
    """
    prices = product_sheet.get("prices") or {}

    def pick_from_voucher_dict(voucher_prices: dict) -> Optional[Tuple[float, float, str]]:
        best = None
        if not isinstance(voucher_prices, dict):
            return None
        for key, vp in voucher_prices.items():
            if not isinstance(vp, dict):
                continue
            v_cur = _safe_float(vp.get("current"))
            v_prev = _safe_float(vp.get("previous"))
            if v_cur > 0 and v_prev > 0 and v_cur < v_prev:
                cand = (v_prev, v_cur, f"voucher:{key}")
                if best is None or (cand[0] - cand[1]) > (best[0] - best[1]):
                    best = cand
        return best

    top = pick_from_voucher_dict(prices.get("voucherPrices") or {})
    if top:
        return top[0], top[1], top[2]

    sizes = product_sheet.get("sizes") or []
    best = None
    for s in sizes:
        if not isinstance(s, dict):
            continue
        cand = pick_from_voucher_dict(s.get("voucherPrices") or {})
        if cand:
            if best is None or (cand[0] - cand[1]) > (best[0] - best[1]):
                best = cand
    if best:
        return best[0], best[1], best[2] + "__from_size"

    cur = _safe_float(prices.get("current"))
    prev = _safe_float(prices.get("previous"))
    if cur > 0 and prev > 0 and cur < prev:
        return prev, cur, "public"

    if cur > 0:
        return cur, cur, "no_discount"

    return 0.0, 0.0, "no_price"


# =========================
# Core: parse one url with existing driver
# =========================
def process_product_url_with_driver(driver, product_url: str):
    print(f"\n🔍 正在访问: {product_url}")
    driver.get(product_url)
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.2)

    dump_debug_page(driver, "PRE__" + product_url[-80:])

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # title
    title_tag = soup.find("title")
    product_title = (
        re.sub(r"\s*[-–—].*", "", title_tag.text.strip())
        if title_tag and title_tag.text
        else "Unknown Title"
    )

    # next_data
    script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
    if not script_tag or not script_tag.string:
        dump_debug_page(driver, "NO_NEXT_DATA")
        raise RuntimeError("未找到 __NEXT_DATA__")

    json_data = json.loads(script_tag.string)
    product_sheet = (
        json_data.get("props", {})
        .get("pageProps", {})
        .get("productSheet")
    )
    if not product_sheet:
        dump_debug_page(driver, "NO_PRODUCT_SHEET")
        raise RuntimeError("未找到 productSheet")

    data = product_sheet
    product_code = data.get("code", "Unknown_Code")
    dump_debug_page(driver, product_code)

    description = data.get("description", "")
    original_price, discount_price, price_src = pick_prices_from_product_sheet(data)

    color_data = data.get("color", "")
    color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

    # features
    features_raw = data.get("features") or []
    feature_texts = []
    for f in features_raw:
        value_html = (f.get("value") or "")
        clean_text = BeautifulSoup(value_html, "html.parser").get_text(strip=True)
        if clean_text:
            feature_texts.append(clean_text)
    feature_str = " | ".join(feature_texts) if feature_texts else "No Data"

    # upper material
    upper_material = "No Data"
    for feature in features_raw:
        name = (feature.get("name") or "").lower()
        if "upper" in name:
            raw_html = feature.get("value") or ""
            upper_material = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
            break

    # sizes
    size_map = {}
    size_detail = {}
    for s in data.get("sizes", []):
        value = (s.get("value", "") or "").strip()
        available = bool(s.get("available", False))
        quantity = s.get("quantity", 0)
        ean = s.get("ean", "")
        size_map[value] = "有货" if available else "无货"
        size_detail[value] = {"stock_count": quantity, "ean": ean}

    gender = infer_gender_from_url(product_url)

    # fill missing sizes
    standard_sizes = SIZE_RANGE_CONFIG.get("camper", {}).get(gender, [])
    if standard_sizes:
        missing = [x for x in standard_sizes if x not in size_detail]
        for x in missing:
            size_map[x] = "无货"
            size_detail[x] = {"stock_count": 0, "ean": ""}
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
        "Source URL": product_url,
        "Price Source": price_src,  # 便于你排查
    }

    out_path = Path(SAVE_PATH) / f"{product_code}.txt"
    format_txt(info, out_path, brand="camper")
    print(f"✅ 完成 TXT: {out_path.name}  (src={price_src}, P={original_price}, D={discount_price})")


# =========================
# v3 Entry: PUBLIC multi-thread (no login)
# =========================
def camper_fetch_product_info(product_urls_file: Optional[str] = None,
                              login_wait_seconds: int = LOGIN_WAIT_SECONDS):
    """
    ✅ 函数名 + 参数保持不变（兼容你外部调用）
    ✅ URL list 读取逻辑保持不变
    ✅ 页面解析逻辑 process_product_url_with_driver 保持不变
    ❗ 仅改：不登录 + 多线程 + 每线程独立driver
    """
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    print(f"📄 使用链接文件: {product_urls_file}")
    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    # 不登录：login_wait_seconds 参数保留但不使用（为了兼容）
    # print(f"ℹ️ Public 模式：不登录，忽略 login_wait_seconds={login_wait_seconds}")

    def worker(url: str):
        driver = None
        try:
            driver = get_driver(name="camper_v3_public_mt", headless=True)
            # 可选预热（如果你发现首个页面偶发超时可开启）
            # driver.get(HOME_URL)
            process_product_url_with_driver(driver, url)
            return True, url, ""
        except Exception as e:
            return False, url, str(e)
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    print(f"🚀 开始多线程抓取：{len(urls)} 条，MAX_WORKERS={MAX_WORKERS}")

    failed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fut_map = {ex.submit(worker, u): u for u in urls}
        for fut in as_completed(fut_map):
            ok, url, err = fut.result()
            if not ok:
                print(f"❌ 失败: {url} - {err}")
                failed.append(url)

    if failed:
        fail_path = Path(SAVE_PATH).resolve().parent / "failed_urls_public_mt.txt"
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        print(f"⚠️ 失败链接已输出: {fail_path}")

    print("✅ 全部完成")


if __name__ == "__main__":
    camper_fetch_product_info()
