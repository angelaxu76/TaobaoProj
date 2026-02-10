# -*- coding: utf-8 -*-
"""
Outdoor & Country | Barbour 商品抓取（v4 - 加速版）
保持对外接口 & pipeline 兼容：
- process_url(url, output_dir)
- outdoorandcountry_fetch_info(max_workers=3)

v4 提速点：
1) 每个 driver 只 accept cookies 一次（避免每页等待）
2) 去掉固定 sleep(3)，改为等待 body 出现 + 短暂停 0.6s
3) 遇到 Cloudflare/挑战页：自动重试 1 次
4) driver 使用 common_taobao.core.selenium_utils（锁死本地 chromedriver，且禁图）
"""

import time
import json
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote

from bs4 import BeautifulSoup

from config import BARBOUR, SETTINGS
from brands.barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# ✅ 统一 TXT 写入
from common_taobao.ingest.txt_writer import format_txt

# ✅ 使用稳定 driver 池（锁死 chromedriver + 线程隔离 key + 禁图）
from common_taobao.core.selenium_utils import get_driver as _get_driver_v2
from common_taobao.core.selenium_utils import quit_all_drivers as _quit_all_drivers_v2

# ✅ 尺码清洗（保守：识别不了就原样返回）
from common_taobao.core.size_utils import clean_size_for_barbour
from brands.barbour.core.site_utils import assert_site_or_raise as canon

CANON_SITE = canon("outdoorandcountry")
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# ========== 浏览器与 Cookie ==========
def accept_cookies(driver, timeout=4):
    """
    v4：每个 driver 只点一次 cookie。
    """
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
        # 找不到也当作已处理，避免每次都等
        driver._cookies_accepted = True


# ========== 工具 ==========
def _normalize_color_from_url(url: str) -> str:
    try:
        qs = parse_qs(urlparse(url).query)
        c = qs.get("c", [None])[0]
        if not c:
            return ""
        c = unquote(c)  # %2F -> /
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
        desc = tag["content"].replace("<br>", "").replace("<br/>", "").replace("<br />", "")
        return desc.strip()
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
    """
    兼容 outdoorandcountry JSON-LD：
    - offers[].mpn 有时是 "MWX0017NY9108"（末尾两位尺码） -> 截掉尺码得到 MWX0017NY91
    - 有时是 "MWX0017NY91" 或 "MWX0017NY91_08"
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = script.string and script.string.strip()
            if not data:
                continue
            j = json.loads(data)

            # list/dict 兼容
            candidates = j if isinstance(j, list) else [j]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                if obj.get("@type") != "Product":
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

                    m = re.search(r'([A-Z]{2}\d{2})(\d{2})$', mpn)
                    if m:
                        return m.group(1)
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


# ========== Outdoor 专属尺码逻辑（保持你现有风格） ==========
WOMEN_NUM = ["6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA = ["S", "M", "L", "XL", "XXL", "XXXL"]
MEN_NUM = [str(s) for s in range(32, 52, 2)]  # 32..50 偶数


def _clean_size(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    s = clean_size_for_barbour(raw) or raw
    return s.strip()


def _build_sizes_from_offers(offers, gender: str):
    """
    offers: [(size_str, price, stock_text, can_order), ...]
    输出：
      Product Size Detail: "6:3:0000000000000;8:0:0000000000000;..."
    v4：只写 Detail，不写 SizeMap
    """
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

        # 过滤 52 及以上男装数字尺码
        m = re.match(r"^(\d{2})$", cs)
        if m and int(m.group(1)) >= 52:
            continue

        temp.append((cs, stock))

    if not temp:
        return "No Data"

    # 去重合并（同尺码取最大库存）
    bucket = {}
    for s, stock in temp:
        bucket[s] = max(bucket.get(s, 0), stock)

    # 排序：女款按 6-20；男款按字母+数字
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

    # 生成 Detail
    out = []
    for s in ordered:
        qty = DEFAULT_STOCK_COUNT if bucket.get(s, 0) > 0 else 0
        out.append(f"{s}:{qty}:0000000000000")

    return ";".join(out) if out else "No Data"


# ========== 多线程 driver 管理（接口不变） ==========
# ========== 多线程 driver 管理（v4.1：定期重启，防止越跑越慢） ==========
_thread_local_driver = threading.local()

# 每个线程跑多少个页面就重启一次 driver（建议 30~80 之间）
_RESTART_EVERY = 50

def create_driver(headless: bool = False):
    return _get_driver_v2(
        name="outdoorandcountry",
        headless=True,
        window_size="1200,1600",
    )

def get_driver(headless: bool = False):
    d = getattr(_thread_local_driver, "driver", None)
    n = getattr(_thread_local_driver, "count", 0)

    # 如果没有 driver，或到达重启阈值，则重建
    if d is None or n >= _RESTART_EVERY:
        try:
            if d is not None:
                d.quit()
        except Exception:
            pass

        d = create_driver(headless=headless)
        _thread_local_driver.driver = d
        _thread_local_driver.count = 0
        return d

    return d

def mark_driver_used():
    _thread_local_driver.count = getattr(_thread_local_driver, "count", 0) + 1

def shutdown_all_drivers():
    _quit_all_drivers_v2()



# ========== v4：挑战页检测 + 轻量重试 ==========
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


def process_url(url, output_dir):
    """
    ✅ 外部接口保持不变：process_url(url, output_dir)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        driver = get_driver()
        print(f"\n🌐 正在抓取: {url}", flush=True)

        # 1) 首次加载（v4：只等 body + 0.6s 短暂停）
        driver.get(url)
        accept_cookies(driver)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(0.6)
        html = driver.page_source

        # 2) 挑战页则重试一次
        if _is_challenge_page(html):
            print("⚠️ 检测到挑战页，重试一次...", flush=True)
            time.sleep(1.2)
            driver.get(url)
            accept_cookies(driver)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(0.6)
            html = driver.page_source

        # 3) 解析（复用你已有解析器）
        info = parse_offer_info(html, url, site_name=CANON_SITE) or {}
        url_color = _normalize_color_from_url(url)

        # 价格字段兼容
        if info.get("original_price_gbp"):
            info["Product Price"] = info["original_price_gbp"]
        if info.get("discount_price_gbp"):
            info["Adjusted Price"] = info["discount_price_gbp"]

        # 4) 基础字段补齐
        info.setdefault("Brand", "Barbour")
        info.setdefault("Product Name", "No Data")
        info.setdefault("Product Color", url_color or "No Data")
        info.setdefault("Product Description", _extract_description(html))
        info.setdefault("Feature", _extract_features(html))
        info.setdefault("Site Name", CANON_SITE)
        info["Source URL"] = url

        # 5) Product Code / Product Color Code（组合码策略）
        color_code = info.get("Product Color Code") or _extract_color_code_from_jsonld(html)
        if color_code:
            info["Product Color Code"] = color_code
            info["Product Code"] = color_code

        # 6) 性别兜底
        if not info.get("Product Gender"):
            info["Product Gender"] = _infer_gender_from_name(info.get("Product Name", ""))

        # 7) Offers → Product Size Detail（只写 Detail）
        offers = info.get("Offers") or []
        info["Product Size Detail"] = _build_sizes_from_offers(offers, info.get("Product Gender") or "")

        # 8) 文件名策略
        if color_code:
            filename = f"{sanitize_filename(color_code)}.txt"
        else:
            safe_name = sanitize_filename(info.get("Product Name", "NoName"))
            safe_color = sanitize_filename(info.get("Product Color", "NoColor"))
            filename = f"{safe_name}_{safe_color}.txt"

        output_dir.mkdir(parents=True, exist_ok=True)
        txt_path = output_dir / filename
        format_txt(info, txt_path, brand="Barbour")
        print(f"✅ 写入: {txt_path.name}", flush=True)

    except Exception as e:
        print(f"❌ 处理失败: {url}\n    {repr(e)}", flush=True)
    finally:
        mark_driver_used()


def outdoorandcountry_fetch_info(max_workers=3):
    """
    ✅ 外部接口保持不变：outdoorandcountry_fetch_info(max_workers=3)
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

    print(f"🔄 启动多线程抓取（v4 加速），总链接数: {len(urls)}，并发线程数: {max_workers}", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_url, url, output_dir) for url in urls]
            for fut in as_completed(futures):
                fut.result()
    finally:
        shutdown_all_drivers()


if __name__ == "__main__":
    outdoorandcountry_fetch_info(max_workers=3)
