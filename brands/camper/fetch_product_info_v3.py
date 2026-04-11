# fetch_product_info_v3.py  (PUBLIC + MULTI-THREAD, STABLE)
# ✅ 保持不变：
# - camper_fetch_product_info(product_urls_file: Optional[str] = None, login_wait_seconds: int = LOGIN_WAIT_SECONDS)
# - URL list 读取逻辑
# - process_product_url_with_driver 页面获取/解析逻辑（仍然用 driver.get + __NEXT_DATA__）
# ✅ 只改动：
# - Chrome/driver 逻辑：每线程一个 driver（thread-local），线程内复用，结束统一 quit
# - 多线程调度：ThreadPoolExecutor

import os
import re
import time
import json
import threading
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CAMPER, SIZE_RANGE_CONFIG
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category
from common.browser.selenium_utils import get_driver

# =========================
# Config
# =========================
HOME_URL = "https://www.camper.com/en_GB"
PRODUCT_URLS_FILE = CAMPER["LINKS_FILE"]
SAVE_PATH = CAMPER["TXT_DIR"]

DEFAULT_MAX_WORKERS = 3  # 6GB 内存机器：3 个 Chrome ≈ 1.5GB，留足系统余量
LOGIN_WAIT_SECONDS = 30  # 参数兼容保留（public 版不登录）

DEBUG_ENABLED = False
IGNORE_VOUCHER = True  # 设为 True 时跳过 voucherPrices，直接使用 prices.current/previous
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
        "WinError 10061" in msg           # 拒绝连接（driver 进程不在了）
        or "Max retries exceeded" in msg
        or "NewConnectionError" in msg
        or "Failed to establish a new connection" in msg
        or ("localhost" in msg and "/session/" in msg)
        or "Read timed out" in msg        # driver 进程崩溃/OOM，120s 无响应
        or "RemoteDisconnected" in msg    # driver 进程意外断开
    )


def dump_debug_page(driver, name: str):
    if not DEBUG_ENABLED:
        return

    safe = re.sub(r"[^\w\-\.]+", "_", name)[:120]
    d = Path(DEBUG_DIR) / safe
    d.mkdir(parents=True, exist_ok=True)

    with open(d / "page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

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

    try:
        with open(d / "cookies.json", "w", encoding="utf-8") as f:
            json.dump(driver.get_cookies(), f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def pick_prices_from_product_sheet(product_sheet: dict) -> Tuple[float, float, str]:
    """
    public 模式下通常没有 voucherPrices，会自动落到 public/no_discount
    （保持你原来的价格逻辑，不动）
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

    if not IGNORE_VOUCHER:
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
# ✅ STABLE CHROME: thread-local driver reuse (关键修复点)
# =========================
drivers_lock = threading.Lock()
_all_drivers = set()
thread_local = threading.local()

def get_thread_driver():
    """
    每个线程只创建一次 driver，并在任务结束统一 quit
    这就是你“原始版 chrome 很好”的核心机制
    """
    if not hasattr(thread_local, "driver") or thread_local.driver is None:
        d = get_driver(name="camper_v3_public_mt", headless=True)
        thread_local.driver = d
        with drivers_lock:
            _all_drivers.add(d)
    return thread_local.driver

def reset_thread_driver():
    """
    线程内 driver 掉线（10061）时，重建一次
    """
    try:
        if hasattr(thread_local, "driver") and thread_local.driver is not None:
            try:
                thread_local.driver.quit()
            except Exception:
                pass
    finally:
        thread_local.driver = None

def shutdown_all_drivers():
    with drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except Exception:
                pass
        _all_drivers.clear()


# =========================
# Core: parse one url with existing driver  (保持不变调用方式)
# =========================
def process_product_url_with_driver(driver, product_url: str):
    print(f"\n🔍 正在访问: {product_url}")
    driver.get(product_url)
    wait = WebDriverWait(driver, 25)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    # 用页面关键数据就绪代替固定 sleep，避免每个商品额外等待 1.2 秒。
    wait.until(
        lambda d: bool(
            d.execute_script(
                """
                const el = document.querySelector('script#__NEXT_DATA__[type="application/json"]');
                return !!(el && el.textContent && el.textContent.trim().length > 0);
                """
            )
        )
    )

    dump_debug_page(driver, "PRE__" + product_url[-80:])

    soup = BeautifulSoup(driver.page_source, "html.parser")

    title_tag = soup.find("title")
    product_title = (
        re.sub(r"\s*[-–—].*", "", title_tag.text.strip())
        if title_tag and title_tag.text
        else "Unknown Title"
    )

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

    features_raw = data.get("features") or []
    feature_texts = []
    for f in features_raw:
        name_text = BeautifulSoup(f.get("name") or "", "html.parser").get_text(strip=True)
        value_text = BeautifulSoup(f.get("value") or "", "html.parser").get_text(strip=True)
        if name_text and value_text:
            feature_texts.append(f"{name_text}: {value_text}")
        elif value_text:
            feature_texts.append(value_text)
        # skip features with name-only (section headers like bare "Outsole")
    feature_str = " | ".join(feature_texts) if feature_texts else "No Data"

    upper_material = "No Data"
    for feature in features_raw:
        name = (feature.get("name") or "").lower()
        if "upper" in name:
            raw_html = feature.get("value") or ""
            upper_material = BeautifulSoup(raw_html, "html.parser").get_text(strip=True)
            break

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
        "Price Source": price_src,
    }

    out_path = Path(SAVE_PATH) / f"{product_code}.txt"
    format_txt(info, out_path, brand="camper")
    print(f"✅ 完成 TXT: {out_path.name}  (src={price_src}, P={original_price}, D={discount_price})")


# =========================
# v3 Entry: PUBLIC multi-thread (no login)  ✅ 签名不变
# =========================
def camper_fetch_product_info(product_urls_file: Optional[str] = None,
                              login_wait_seconds: int = LOGIN_WAIT_SECONDS,
                              max_workers: int = DEFAULT_MAX_WORKERS,
                              debug_enabled: Optional[bool] = None,
                              links_file: Optional[str] = None):
    del login_wait_seconds  # public 版保留兼容签名，但不使用

    global DEBUG_ENABLED

    if links_file is not None:
        product_urls_file = links_file
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE
    if debug_enabled is not None:
        DEBUG_ENABLED = debug_enabled
    if not isinstance(max_workers, int) or max_workers < 1:
        raise ValueError(f"max_workers must be a positive int, got: {max_workers!r}")

    print(f"📄 使用链接文件: {product_urls_file}")
    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"🚀 开始多线程抓取：{len(urls)} 条，MAX_WORKERS={max_workers}，DEBUG_ENABLED={DEBUG_ENABLED}")

    failed = []

    def worker(url: str):
        # 每个线程复用自己的 driver；掉线就重建一次再试
        for attempt in range(2):
            driver = get_thread_driver()
            try:
                process_product_url_with_driver(driver, url)
                return True, url, ""
            except Exception as e:
                if is_driver_connection_error(e) and attempt == 0:
                    print(f"⚠️ driver 掉线(10061)，重建后重试: {url}")
                    reset_thread_driver()
                    time.sleep(0.5)
                    continue
                return False, url, str(e)
        return False, url, "unknown"

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(worker, u): u for u in urls}
            for fut in as_completed(fut_map):
                ok, url, err = fut.result()
                if not ok:
                    print(f"❌ 失败: {url} - {err}")
                    failed.append(url)
    finally:
        shutdown_all_drivers()

    if failed:
        fail_path = Path(SAVE_PATH).resolve().parent / "failed_urls_public_mt.txt"
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        print(f"⚠️ 失败链接已输出: {fail_path}")

    print("✅ 全部完成")


if __name__ == "__main__":
    camper_fetch_product_info()
