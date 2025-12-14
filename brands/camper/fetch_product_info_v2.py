# fetch_product_info_v2_2.py
import os
import re
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CAMPER, SIZE_RANGE_CONFIG
from common_taobao.ingest.txt_writer import format_txt
from common_taobao.core.category_utils import infer_style_category
from common_taobao.core.selenium_utils import get_driver, quit_all_drivers

DEBUG_ENABLED = False   # True=开启 debug，False=关闭 debug
# =========================
# Config
# =========================
HOME_URL = "https://www.camper.com/en_GB"
PRODUCT_URLS_FILE = CAMPER["LINKS_FILE"]
SAVE_PATH = CAMPER["TXT_DIR"]

MAX_WORKERS = 6
DEBUG_DIR = str(Path(SAVE_PATH).resolve().parent / "debug_camper")
Path(DEBUG_DIR).mkdir(parents=True, exist_ok=True)
print("🧪 DEBUG_DIR =", DEBUG_DIR)

os.makedirs(SAVE_PATH, exist_ok=True)

# 全局 cookies（主线程登录后赋值；子线程读取）
LOGIN_COOKIES: list[dict] = []


# =========================
# Debug dump
# =========================
def dump_debug_page(driver, product_code: str, base_dir=DEBUG_DIR):

    if not DEBUG_ENABLED:
        return

    debug_dir = Path(base_dir) / str(product_code)
    debug_dir.mkdir(parents=True, exist_ok=True)

    # 1) HTML
    with open(debug_dir / "page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    # 2) __NEXT_DATA__
    soup = BeautifulSoup(driver.page_source, "html.parser")
    next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if next_data_tag and next_data_tag.string:
        try:
            next_json = json.loads(next_data_tag.string)
            with open(debug_dir / "next_data.json", "w", encoding="utf-8") as f:
                json.dump(next_json, f, indent=2, ensure_ascii=False)
        except Exception as e:
            with open(debug_dir / "next_data_error.txt", "w", encoding="utf-8") as f:
                f.write(str(e))

    # 3) Cookies
    cookies = driver.get_cookies()
    with open(debug_dir / "cookies.json", "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)

    # 4) Meta quick check
    meta_lines = []
    meta_lines.append(f"URL: {driver.current_url}")
    meta_lines.append(f"Cookies count: {len(cookies)}")
    if next_data_tag and next_data_tag.string:
        meta_lines.append("voucherPrices: " + ("FOUND" if "voucherPrices" in next_data_tag.string else "NOT FOUND"))
    page_lower = driver.page_source.lower()
    meta_lines.append("login_hint: " + ("maybe_logged_in" if ("logout" in page_lower or "my account" in page_lower) else "unknown"))

    with open(debug_dir / "meta.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(meta_lines))

    print(f"🧪 Debug dump saved to: {debug_dir}")


# =========================
# Helpers
# =========================
def infer_gender_from_url(url: str) -> str:
    url = url.lower()
    if "/women/" in url:
        return "女款"
    if "/men/" in url:
        return "男款"
    if "/kids/" in url or "/children/" in url:
        return "童款"
    return "未知"


def _safe_float(v):
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def pick_prices_from_product_sheet(product_sheet: dict):
    prices = product_sheet.get("prices") or {}

    def pick_from_voucher_dict(voucher_prices: dict):
        best = None  # (prev, cur, key)
        if not isinstance(voucher_prices, dict):
            return None
        for key, vp in voucher_prices.items():
            if not isinstance(vp, dict):
                continue
            v_cur = _safe_float(vp.get("current"))
            v_prev = _safe_float(vp.get("previous"))
            if v_cur > 0 and v_prev > 0 and v_cur < v_prev:
                cand = (v_prev, v_cur, f"voucher:{key}")
                # 选折扣力度最大的
                if best is None or (cand[0] - cand[1]) > (best[0] - best[1]):
                    best = cand
        return best

    # 1) 顶层 voucherPrices（最理想）
    top = pick_from_voucher_dict(prices.get("voucherPrices") or {})
    if top:
        return top[0], top[1], top[2]

    # 2) 尺码层 voucherPrices 兜底（有些款折扣只挂在 size 上）
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

    # 3) public previous/current
    cur = _safe_float(prices.get("current"))
    prev = _safe_float(prices.get("previous"))
    if cur > 0 and prev > 0 and cur < prev:
        return prev, cur, "public"

    # 4) no discount（关键：不能让 Product Price=0）
    if cur > 0:
        return cur, cur, "no_discount"

    return 0.0, 0.0, "no_price"


def apply_cookies_to_driver(driver, cookies: list[dict]):
    """把主线程 cookies 注入到子线程 driver"""
    if not cookies:
        return

    driver.get(HOME_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    time.sleep(1.5)

    # ✅ 不依赖解析，先把真实访问到的页面落盘（避免异常导致没 dump）
    safe_name = "PRE__" + re.sub(r"\W+", "_", HOME_URL)[-80:]
    dump_debug_page(driver, safe_name, base_dir=DEBUG_DIR)

    for c in cookies:
        if not isinstance(c, dict):
            continue
        c2 = dict(c)
        c2.pop("sameSite", None)
        if "expiry" in c2 and c2["expiry"] is not None:
            try:
                c2["expiry"] = int(c2["expiry"])
            except Exception:
                c2.pop("expiry", None)
        try:
            driver.add_cookie(c2)
        except Exception:
            pass

    driver.get(HOME_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))


def init_camper_login_cookies(wait_seconds: int = 30):
    """打开首页，给 30 秒手动登录，保存 cookies"""
    global LOGIN_COOKIES
    print("=" * 80)
    print("🔐 [Camper Login] 将打开官网首页，请在浏览器里手动完成登录。")
    print(f"⏳ 你有 {wait_seconds} 秒完成登录。")
    print("✅ 登录完成后不需要点任何按钮，脚本会自动继续并共享 cookie 给多线程。")
    print("=" * 80)

    driver = None
    try:
        driver = get_driver(name="camper_login", headless=False)
        driver.get(HOME_URL)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(wait_seconds)
        LOGIN_COOKIES = driver.get_cookies() or []
        print(f"🍪 已获取 cookies 数量: {len(LOGIN_COOKIES)}")
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


# =========================
# Core
# =========================
def process_product_url(product_url: str):
    driver = None
    try:
        driver = get_driver(name="camper", headless=True)

        # 注入登录态
        if LOGIN_COOKIES:
            apply_cookies_to_driver(driver, LOGIN_COOKIES)

        print(f"\n🔍 正在访问: {product_url}")
        driver.get(product_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 先找 __NEXT_DATA__
        script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
        if not script_tag or not script_tag.string:
            dump_debug_page(driver, "NO_NEXT_DATA")
            print("⚠️ 未找到 __NEXT_DATA__ JSON")
            return

        json_data = json.loads(script_tag.string)
        product_sheet = (
            json_data.get("props", {})
            .get("pageProps", {})
            .get("productSheet")
        )
        if not product_sheet:
            dump_debug_page(driver, "NO_PRODUCT_SHEET")
            print(f"⚠️ 未找到 productSheet，跳过: {product_url}")
            return

        data = product_sheet
        product_code = data.get("code", "Unknown_Code")

        # ✅ 关键：现在 product_code 已经有了，再 dump
        dump_debug_page(driver, product_code)

        # ✅ 关键：product_title 必须定义（你现在就是缺了这个）
        title_tag = soup.find("title")
        product_title = (
            re.sub(r"\s*[-–—].*", "", title_tag.text.strip())
            if title_tag and title_tag.text
            else data.get("name") or "Unknown Title"
        )

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
            "Price Source": price_src,  # 方便排查
        }

        save_dir = Path(SAVE_PATH)
        save_dir.mkdir(parents=True, exist_ok=True)
        out_path = save_dir / f"{product_code}.txt"
        format_txt(info, out_path, brand="camper")
        print(f"✅ 完成 TXT: {out_path.name}  (src={price_src}, P={original_price}, D={discount_price})")

    except Exception as e:
        try:
            if driver:
                dump_debug_page(driver, "EXCEPTION")
        except Exception:
            pass
        print(f"❌ 错误: {product_url} - {e}")

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


def camper_fetch_product_info(product_urls_file=None, max_workers=MAX_WORKERS, login_wait_seconds: int = 30):
    if product_urls_file is None:
        product_urls_file = PRODUCT_URLS_FILE

    print(f"📄 使用链接文件: {product_urls_file}")
    with open(product_urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    init_camper_login_cookies(wait_seconds=login_wait_seconds)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_product_url, u) for u in urls]
            for fu in as_completed(futures):
                fu.result()
    finally:
        quit_all_drivers()


if __name__ == "__main__":
    camper_fetch_product_info()
