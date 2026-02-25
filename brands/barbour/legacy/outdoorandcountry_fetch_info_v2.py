# -*- coding: utf-8 -*-
"""
Outdoor & Country | Barbour 商品抓取（v4.2 - 稳定长跑版）
保持对外接口兼容：
- process_url(url, output_dir)
- outdoorandcountry_fetch_info(max_workers=3)

v4.2 解决点：
1) driver 长跑退化：每线程跑 N 个页面自动重启 driver（默认 20）
2) 风控越来越严：挑战页/超时/失败 -> 随机退避 + 指数退避（避免越跑越慢）
3) 并发自适应：失败多时自动把有效并发压到 2（即使你传更大）
"""

import time
import json
import threading
import re
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote

from bs4 import BeautifulSoup

from config import BARBOUR, SETTINGS
from brands.barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info
from common.ingest.txt_writer import format_txt

# ✅ 使用稳定 driver 池（锁死本地 chromedriver + 线程隔离 key + 禁图）
from common.core.selenium_utils import get_driver as _get_driver_v2
from common.core.selenium_utils import quit_all_drivers as _quit_all_drivers_v2

from common.core.size_utils import clean_size_for_barbour
from brands.barbour.core.site_utils import assert_site_or_raise as canon

CANON_SITE = canon("outdoorandcountry")
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# ======================
# v4.2 关键参数（可按需微调）
# ======================
RESTART_EVERY = 20        # ✅ 每线程跑多少页面重启 driver（越小越稳，但会慢一点）
EFFECTIVE_MAX_WORKERS = 2 # ✅ Outdoor 强风控站点：长期稳定建议 2
PAGE_WAIT_TIMEOUT = 10
AFTER_BODY_SLEEP = 0.6

# 退避策略（挑战页/失败时）
BACKOFF_BASE = 3.0
BACKOFF_JITTER = (0.8, 1.6)   # 乘数随机抖动范围
BACKOFF_CAP = 25.0           # 最长退避秒数

# 全局失败统计（用于自适应降并发/更强退避）
_stats_lock = threading.Lock()
_stats = {
    "ok": 0,
    "fail": 0,
    "challenge": 0,
    "last_fail_ts": 0.0,
}

def _inc_stat(key: str):
    with _stats_lock:
        _stats[key] += 1
        if key in ("fail", "challenge"):
            _stats["last_fail_ts"] = time.time()

def _fail_ratio() -> float:
    with _stats_lock:
        ok = _stats["ok"]
        fail = _stats["fail"] + _stats["challenge"]
        total = ok + fail
        return (fail / total) if total else 0.0

def _compute_backoff(tries: int, kind: str) -> float:
    """
    tries: 当前 url 的重试次数（0,1,2...）
    kind: "challenge" or "fail"
    """
    # 指数退避：base * (2^tries) * jitter
    jitter = random.uniform(*BACKOFF_JITTER)
    sec = BACKOFF_BASE * (2 ** tries) * jitter

    # 如果全局失败率高，增加退避（越跑越慢时很关键）
    ratio = _fail_ratio()
    if ratio >= 0.25:
        sec *= 1.4
    if ratio >= 0.40:
        sec *= 1.8

    # 挑战页比普通失败更强退避
    if kind == "challenge":
        sec *= 1.5

    return min(sec, BACKOFF_CAP)


# ========== Cookie：每个 driver 只点一次 ==========
def accept_cookies(driver, timeout=4):
    if getattr(driver, "_cookies_accepted", False):
        return

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        btn.click()
        driver._cookies_accepted = True
        time.sleep(0.2)
    except Exception:
        driver._cookies_accepted = True


# ========== utils ==========
def _normalize_color_from_url(url: str) -> str:
    try:
        qs = parse_qs(urlparse(url).query)
        c = qs.get("c", [None])[0]
        if not c:
            return ""
        c = unquote(c)
        c = c.replace("\\", "/")
        c = re.sub(r"\s*/\s*", " / ", c)
        c = re.sub(r"\s+", " ", c).strip()
        c = " ".join(w.capitalize() for w in c.split(" "))
        return c
    except Exception:
        return ""

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name or "NoName")

def _extract_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        return tag["content"].replace("<br>", "").replace("<br/>", "").replace("<br />", "").strip()
    tab = soup.select_one(".product_tabs .tab_content[data-id='0'] div")
    return tab.get_text(" ", strip=True) if tab else "No Data"

def _extract_features(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h3 = soup.find("h3", attrs={"title": "Features"})
    if h3:
        ul = h3.find_next("ul")
        if ul:
            items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
            return "; ".join(items)
    return "No Data"

def _extract_color_code_from_jsonld(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = (script.string or "").strip()
            if not raw:
                continue
            j = json.loads(raw)
            candidates = j if isinstance(j, list) else [j]
            for obj in candidates:
                if not isinstance(obj, dict) or obj.get("@type") != "Product":
                    continue
                offers = obj.get("offers")
                if not offers:
                    continue
                offers_list = offers if isinstance(offers, list) else [offers]
                for off in offers_list:
                    mpn = (off or {}).get("mpn")
                    if not isinstance(mpn, str):
                        continue
                    mpn = mpn.split("_")[0].strip()

                    if len(mpn) >= 11:
                        maybe_code = mpn[:-2]
                        if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2}$", maybe_code):
                            return maybe_code
        except Exception:
            continue
    return ""

def _infer_gender_from_name(name: str) -> str:
    n = (name or "").lower()
    if any(x in n for x in ["women", "women's", "womens", "ladies", "lady"]):
        return "女款"
    if any(x in n for x in ["men", "men's", "mens"]):
        return "男款"
    if any(x in n for x in ["kids", "kid", "boy", "girl"]):
        return "童款"
    return "男款"

def _is_challenge_page(html: str) -> bool:
    low = (html or "").lower()
    return (
        "checking your browser" in low
        or "attention required" in low
        or "cloudflare" in low
        or "access denied" in low
        or "captcha" in low
        or "<title>just a moment" in low
    )


# ========== 尺码整理 ==========
WOMEN_NUM = ["6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA = ["S", "M", "L", "XL", "XXL", "XXXL"]
MEN_NUM = [str(s) for s in range(32, 52, 2)]

def _clean_size(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    s = clean_size_for_barbour(raw) or raw
    return s.strip()

def _build_sizes_from_offers(offers, gender: str):
    if not offers:
        return "No Data"

    temp = []
    for size, price, stock_text, can_order in offers:
        size = (size or "").strip()
        if not size:
            continue

        stock = 0
        if (stock_text or "").strip().lower() in ("in stock", "available"):
            stock = DEFAULT_STOCK_COUNT
        if can_order and stock == 0:
            stock = DEFAULT_STOCK_COUNT

        cs = _clean_size(size)
        if not cs:
            continue

        m = re.match(r"^(\d{2})$", cs)
        if m and int(m.group(1)) >= 52:
            continue

        temp.append((cs, stock))

    if not temp:
        return "No Data"

    bucket = {}
    for s, stock in temp:
        bucket[s] = max(bucket.get(s, 0), stock)

    ordered = []
    if "女" in (gender or ""):
        for s in WOMEN_NUM:
            if s in bucket:
                ordered.append(s)
        for s in bucket:
            if s not in ordered:
                ordered.append(s)
    else:
        for s in MEN_ALPHA:
            if s in bucket:
                ordered.append(s)
        for s in MEN_NUM:
            if s in bucket:
                ordered.append(s)
        for s in bucket:
            if s not in ordered:
                ordered.append(s)

    out = []
    for s in ordered:
        qty = DEFAULT_STOCK_COUNT if bucket.get(s, 0) > 0 else 0
        out.append(f"{s}:{qty}:0000000000000")

    return ";".join(out) if out else "No Data"


# ========== v4.2 driver 管理：定期重启（防止越跑越慢） ==========
_thread_local = threading.local()

def create_driver(headless: bool = False):
    # 强制 headless 更省资源
    return _get_driver_v2(
        name="outdoorandcountry",
        headless=True,
        window_size="1200,1600",
    )

def get_driver(headless: bool = False):
    d = getattr(_thread_local, "driver", None)
    cnt = getattr(_thread_local, "count", 0)

    if d is None or cnt >= RESTART_EVERY:
        try:
            if d is not None:
                d.quit()
        except Exception:
            pass

        d = create_driver(headless=headless)
        _thread_local.driver = d
        _thread_local.count = 0

    return d

def mark_driver_used():
    _thread_local.count = getattr(_thread_local, "count", 0) + 1

def shutdown_all_drivers():
    _quit_all_drivers_v2()


# ========== 核心抓取：带自适应退避 & 单 URL 重试 ==========
def process_url(url, output_dir):
    """
    ✅ 外部接口不变：process_url(url, output_dir)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    tries = 0
    max_tries = 2  # 单 URL 最多重试 2 次（总 3 次尝试）

    try:
        while True:
            driver = get_driver()
            print(f"\n🌐 正在抓取: {url} (try={tries})", flush=True)

            try:
                driver.get(url)
                accept_cookies(driver)

                WebDriverWait(driver, PAGE_WAIT_TIMEOUT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(AFTER_BODY_SLEEP)
                html = driver.page_source

                # 挑战页 -> 退避 + 重试
                if _is_challenge_page(html):
                    _inc_stat("challenge")
                    if tries >= max_tries:
                        raise RuntimeError("Challenge page (Cloudflare) - give up")
                    backoff = _compute_backoff(tries, "challenge")
                    print(f"⚠️ 挑战页，退避 {backoff:.1f}s 后重试", flush=True)
                    time.sleep(backoff)
                    tries += 1
                    continue

                # 正常解析
                info = parse_offer_info(html, url, site_name=CANON_SITE) or {}
                url_color = _normalize_color_from_url(url)

                if info.get("original_price_gbp"):
                    info["Product Price"] = info["original_price_gbp"]
                if info.get("discount_price_gbp"):
                    info["Adjusted Price"] = info["discount_price_gbp"]

                info.setdefault("Brand", "Barbour")
                info.setdefault("Product Name", "No Data")
                info.setdefault("Product Color", url_color or "No Data")
                info.setdefault("Product Description", _extract_description(html))
                info.setdefault("Feature", _extract_features(html))
                info.setdefault("Site Name", CANON_SITE)
                info["Source URL"] = url

                color_code = info.get("Product Color Code") or _extract_color_code_from_jsonld(html)
                if color_code:
                    info["Product Color Code"] = color_code
                    info["Product Code"] = color_code

                if not info.get("Product Gender"):
                    info["Product Gender"] = _infer_gender_from_name(info.get("Product Name", ""))

                offers = info.get("Offers") or []
                info["Product Size Detail"] = _build_sizes_from_offers(offers, info.get("Product Gender") or "")

                if color_code:
                    filename = f"{sanitize_filename(color_code)}.txt"
                else:
                    safe_name = sanitize_filename(info.get("Product Name", "NoName"))
                    safe_color = sanitize_filename(info.get("Product Color", "NoColor"))
                    filename = f"{safe_name}_{safe_color}.txt"

                output_dir.mkdir(parents=True, exist_ok=True)
                txt_path = output_dir / filename
                format_txt(info, txt_path, brand="Barbour")

                _inc_stat("ok")
                print(f"✅ 写入: {txt_path.name}", flush=True)
                return

            except Exception as e:
                _inc_stat("fail")
                if tries >= max_tries:
                    raise
                backoff = _compute_backoff(tries, "fail")
                print(f"⚠️ 失败: {repr(e)}\n   退避 {backoff:.1f}s 后重试", flush=True)
                time.sleep(backoff)
                tries += 1
                continue

    except Exception as final_e:
        print(f"❌ 处理失败: {url}\n    {repr(final_e)}", flush=True)

    finally:
        # ✅ 每个 URL 计数一次，用于定期重启 driver
        mark_driver_used()


def outdoorandcountry_fetch_info(max_workers=3):
    """
    ✅ 外部接口不变：outdoorandcountry_fetch_info(max_workers=3)
    """
    links_file = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
    output_dir = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = []
    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u:
                urls.append(u)

    # v4.2：有效并发上限（Outdoor 强风控，长期跑 2 最稳）
    effective = min(int(max_workers), EFFECTIVE_MAX_WORKERS)

    print(f"🔄 启动多线程抓取（v4.2），总链接数: {len(urls)}，请求并发: {max_workers}，有效并发: {effective}", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=effective) as executor:
            futures = [executor.submit(process_url, url, output_dir) for url in urls]
            for fut in as_completed(futures):
                fut.result()
    finally:
        shutdown_all_drivers()


if __name__ == "__main__":
    outdoorandcountry_fetch_info(max_workers=2)
