# fetch_product_info_v4.py
# v4 vs v3:
# - 价格提取顺序：window.__NEXT_DATA__（JS运行时）→ JSON-LD → SSR __NEXT_DATA__
# - window.__NEXT_DATA__ 通过 execute_script 读取，比 HTML 里的 SSR 版本更新，
#   Next.js 客户端水化后可能已补入 prices.previous
# - JSON-LD offers.price 是当前实际生效价格（打折商品即折扣价），
#   与 SSR prices.current 对比即可判断是否有折扣
# - 基础架构与 v3 相同（thread-local Selenium，多线程并发）
import gc
import os
import re
import time
import random
import json
import threading
from pathlib import Path
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CAMPER, SIZE_RANGE_CONFIG
from common.ingest.txt_writer import format_txt
from common.product.category_utils import infer_style_category
from common.browser.driver_auto import build_uc_driver

PRODUCT_URLS_FILE = Path(CAMPER["LINKS_FILE"])
SAVE_PATH = Path(CAMPER["TXT_DIR"])
SAVE_PATH.mkdir(parents=True, exist_ok=True)

DEFAULT_MAX_WORKERS = 3


# ---------------------------
# 工具函数
# ---------------------------

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


def infer_gender_from_url(url: str) -> str:
    u = url.lower()
    if "/women/" in u:
        return "女款"
    if "/men/" in u:
        return "男款"
    if "/kids/" in u or "/children/" in u:
        return "童款"
    return "未知"


def is_driver_error(e: Exception) -> bool:
    msg = str(e)
    return any(k in msg for k in (
        "WinError 10061", "Max retries exceeded", "NewConnectionError",
        "Failed to establish a new connection", "/session/",
        "Read timed out", "RemoteDisconnected",
        "receiving message from renderer", "chrome not reachable",
    ))


# ---------------------------
# 价格提取（三层降级）
# ---------------------------

def _pick_prices_from_sheet(ps: dict) -> Tuple[float, float, str]:
    """从 productSheet dict 读 previous/current。"""
    prices = ps.get("prices") or {}
    prev = _num(prices.get("previous"))
    curr = _num(prices.get("current"))
    if prev > 0 and curr > 0 and prev != curr:
        orig, sale = (prev, curr) if prev > curr else (curr, prev)
        return orig, sale, "sheet_prev_curr"
    if curr > 0:
        return curr, curr, "sheet_curr_only"
    if prev > 0:
        return prev, prev, "sheet_prev_only"
    return 0.0, 0.0, "sheet_no_price"


def _pick_voucher_price(ps: dict) -> Tuple[float, float, str]:
    """从 productSheet.voucherPrices 取最低折扣价（如 PRIVATESALESS26）。"""
    voucher_prices = ps.get("voucherPrices") or {}
    best_sale = float("inf")
    best_orig = 0.0
    best_key = ""
    for key, vp in voucher_prices.items():
        if not isinstance(vp, dict):
            continue
        curr = _num(vp.get("current"))
        prev = _num(vp.get("previous"))
        if curr > 0 and prev > 0 and prev > curr and curr < best_sale:
            best_sale, best_orig, best_key = round(curr, 2), round(prev, 2), key
    if best_key:
        return best_orig, best_sale, f"voucher_{best_key}"
    return 0.0, 0.0, ""


def extract_prices_v4(driver, ssr_product_sheet: dict) -> Tuple[float, float, str]:
    """
    四层价格提取，按可靠性降序：

    0. SSR voucherPrices（最直接的折扣信号，如 PRIVATESALESS26）
       current=96, previous=120 → orig=120, sale=96

    1. window.__NEXT_DATA__（JS 运行时）
       Next.js 客户端水化后 prices.previous 可能已补入折扣信息

    2. JSON-LD offers.price（实际生效价格）
       与 SSR prices.current 做对比：两者不同 → 检测到折扣
       json_ld_price < ssr_current → original=ssr_current, sale=json_ld_price

    3. SSR productSheet prices（HTML 里的 __NEXT_DATA__，最后兜底）
    """

    # --- 0. voucherPrices（SSR 里直接有折扣数据） ---
    orig, sale, src = _pick_voucher_price(ssr_product_sheet)
    if orig > 0:
        print(f"   💰 [voucher] orig={orig}, sale={sale}, key={src}")
        return orig, sale, src

    # --- 1. window.__NEXT_DATA__ via JS ---
    try:
        runtime = driver.execute_script("return window.__NEXT_DATA__")
        if runtime:
            rt_ps = (runtime.get("props", {})
                            .get("pageProps", {})
                            .get("productSheet") or {})
            orig, sale, src = _pick_prices_from_sheet(rt_ps)
            if orig > 0 and orig != sale:
                print(f"   💰 [runtime_nextdata] orig={orig}, sale={sale}")
                return orig, sale, "runtime_nextdata"
            if orig > 0:
                # runtime 也只有一个价格，继续往下
                pass
    except Exception as e:
        print(f"   ⚠️ window.__NEXT_DATA__ 读取失败: {e}")

    # --- 2. JSON-LD offers.price ---
    try:
        ld_price_raw = driver.execute_script("""
            var scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (var i = 0; i < scripts.length; i++) {
                try {
                    var d = JSON.parse(scripts[i].textContent || scripts[i].innerHTML);
                    if (d && d.offers) {
                        var o = Array.isArray(d.offers) ? d.offers[0] : d.offers;
                        if (o && o.price !== undefined) return String(o.price);
                    }
                } catch(e) {}
            }
            return null;
        """)
        if ld_price_raw:
            ld_price = _num(ld_price_raw)
            # SSR current 是基础价格，ld_price 是当前生效价格
            ssr_curr = _num((ssr_product_sheet.get("prices") or {}).get("current"))
            print(f"   💰 [jsonld] ld_price={ld_price}, ssr_current={ssr_curr}")
            if ld_price > 0 and ssr_curr > 0 and ssr_curr > ld_price:
                # 折扣：原价=ssr_current，折扣价=ld_price
                return ssr_curr, ld_price, "jsonld_vs_ssr"
            if ld_price > 0:
                # 没有折扣（或无法确定原价），以 ld_price 作为唯一价格
                orig = max(ld_price, ssr_curr)
                return orig, ld_price, "jsonld_nodiscount"
    except Exception as e:
        print(f"   ⚠️ JSON-LD 读取失败: {e}")

    # --- 3. SSR productSheet（兜底）---
    orig, sale, src = _pick_prices_from_sheet(ssr_product_sheet)
    print(f"   💰 [ssr_fallback] orig={orig}, sale={sale}")
    return orig, sale, src


# ---------------------------
# 特征 & 材质 & 尺码
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
# Selenium 线程池管理（与 v3 相同）
# ---------------------------

drivers_lock = threading.Lock()
_all_drivers: set = set()
thread_local = threading.local()

# 禁用 Chrome 缓存，防止访问大量页面后内存持续堆积
_MEMORY_FLAGS = [
    "--disable-cache",
    "--disable-application-cache",
    "--disable-offline-load-stale-cache",
    "--disk-cache-size=0",
    "--disable-gpu",
    "--disable-dev-shm-usage",
]


def get_thread_driver():
    if not hasattr(thread_local, "driver") or thread_local.driver is None:
        d = build_uc_driver(headless=True, extra_options=_MEMORY_FLAGS)
        thread_local.driver = d
        with drivers_lock:
            _all_drivers.add(d)
    return thread_local.driver


def reset_thread_driver():
    d = getattr(thread_local, "driver", None)
    thread_local.driver = None
    if d:
        with drivers_lock:
            _all_drivers.discard(d)
        try:
            d.quit()
        except Exception:
            pass


def shutdown_all_drivers():
    with drivers_lock:
        drivers = list(_all_drivers)
        _all_drivers.clear()
    for d in drivers:
        try:
            d.quit()
        except Exception:
            pass


# ---------------------------
# 单 URL 处理
# ---------------------------

def process_product_url(driver, url: str):
    print(f"\n🔍 正在访问: {url}")
    driver.get(url)

    wait = WebDriverWait(driver, 25)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    wait.until(lambda d: bool(d.execute_script(
        "var el=document.querySelector('script#__NEXT_DATA__');"
        "return !!(el && el.textContent && el.textContent.trim().length > 0);"
    )))

    soup = BeautifulSoup(driver.page_source, "html.parser")

    title_tag = soup.find("title")
    product_title = (
        re.sub(r"\s*[-–—].*", "", title_tag.text.strip())
        if title_tag and title_tag.text
        else "Unknown Title"
    )

    script_tag = soup.find("script", {"id": "__NEXT_DATA__", "type": "application/json"})
    if not script_tag or not script_tag.string:
        raise RuntimeError("未找到 __NEXT_DATA__")

    json_data = json.loads(script_tag.string)
    ssr_product_sheet = (
        json_data.get("props", {})
                 .get("pageProps", {})
                 .get("productSheet")
    )
    # 释放大 JSON 和 soup（productSheet 已提取出来，原始对象不再需要）
    del json_data, soup, script_tag
    if not ssr_product_sheet:
        raise RuntimeError("未找到 productSheet")

    product_code = ssr_product_sheet.get("code", "Unknown_Code")
    description = ssr_product_sheet.get("description", "") or ""

    original_price, discount_price, price_src = extract_prices_v4(driver, ssr_product_sheet)

    color_data = ssr_product_sheet.get("color", "")
    color = color_data.get("name", "") if isinstance(color_data, dict) else str(color_data)

    feature_str, upper_material = extract_features_and_upper(ssr_product_sheet)
    size_map, size_detail = extract_sizes(ssr_product_sheet)

    gender = infer_gender_from_url(url)
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
        "Source URL": url,
    }

    out_path = SAVE_PATH / f"{product_code}.txt"
    format_txt(info, out_path, brand="camper")
    # 释放 productSheet 和 info（写完 TXT 后不再需要）
    del ssr_product_sheet, info
    gc.collect()
    disc_label = "no_discount" if original_price == discount_price else "DISCOUNT"
    print(f"✅ 完成 TXT: {out_path.name}  [{disc_label}] src={price_src}  P={original_price:.2f}, D={discount_price:.2f}")


# ---------------------------
# Worker（带 driver 重建重试）
# ---------------------------

def _worker(url: str) -> tuple[bool, str, str]:
    for attempt in range(2):
        driver = get_thread_driver()
        try:
            process_product_url(driver, url)
            time.sleep(random.uniform(1.5, 3.0))
            return True, url, ""
        except Exception as e:
            if is_driver_error(e) and attempt == 0:
                print(f"⚠️ driver 掉线，重建后重试: {url}")
                reset_thread_driver()
                time.sleep(random.uniform(2.0, 4.0))
                continue
            return False, url, str(e)
    return False, url, "unknown"


# ---------------------------
# 入口函数（签名与 v2/v3 兼容）
# ---------------------------

def camper_fetch_product_info(
    links_file: Optional[str] = None,
    urls=None,
    max_workers: int = DEFAULT_MAX_WORKERS,
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

    RESTART_EVERY = 20  # 每处理 N 个 URL 重启 Chrome，释放进程内存

    failed = []
    try:
        if max_workers == 1:
            for i, url in enumerate(url_list):
                if i > 0 and i % RESTART_EVERY == 0:
                    print(f"🔄 [{i}/{len(url_list)}] 重启 Chrome 释放内存...")
                    reset_thread_driver()
                ok, u, err = _worker(url)
                if not ok:
                    print(f"❌ 失败: {u} | {err}")
                    failed.append(u)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                for ok, url, err in ex.map(_worker, url_list):
                    if not ok:
                        print(f"❌ 失败: {url} | {err}")
                        failed.append(url)
    finally:
        shutdown_all_drivers()

    if failed:
        fail_path = SAVE_PATH.parent / "failed_urls_v4.txt"
        fail_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"⚠️ 失败链接已输出: {fail_path}")

    print(f"\n✅ 全部完成，失败 {len(failed)} 条")


if __name__ == "__main__":
    camper_fetch_product_info()
