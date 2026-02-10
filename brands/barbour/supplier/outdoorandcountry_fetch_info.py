# -*- coding: utf-8 -*-
"""
Outdoor & Country | Barbour 商品抓取（统一 TXT 模板版）
保持对外接口 & pipeline 兼容：
- process_url(url, output_dir)
- fetch_outdoor_product_offers_concurrent(max_workers=3)

改动要点：
1) 复用你已有的 parse_offer_info(html, url) 解析站点
2) 落盘统一走 txt_writer.format_txt（与其它站点一致）
3) 写入前统一字段：
   - Product Code = Product Color Code（你当前的组合码策略）
   - Site Name = "Outdoor and Country"
   - 不写 SizeMap
   - 过滤 52 及更大的男装数字尺码
4) 类目兜底：遇到 wax + jacket 或 code 前缀 MWX/LWX 时，强制 "waxed jacket"
   - 否则按你在 category_utils 中的旧逻辑
5) Outdoor 专属的价格处理（当页面上无 price 字段时，从 offers 补齐）
6) 尺码行统一：
   - 不写 SizeMap，只写 Product Size Detail
   - 对 Product Size / Product Size Detail 的尺码做清洗
   - 若无 Product Size Detail，按 Size 兜底生成（有货=3/无货=0，EAN 占位）
"""

import time
import json
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote

import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from config import BARBOUR
from brands.barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# ✅ 统一 TXT 写入（与其它站点一致）
from common_taobao.ingest.txt_writer import format_txt
from common_taobao.core.selenium_utils import get_driver, quit_all_drivers

# ✅ 尺码清洗（保守：识别不了就原样返回）
from common_taobao.core.size_utils import clean_size_for_barbour  # 见你上传的实现
from brands.barbour.core.site_utils import assert_site_or_raise as canon
CANON_SITE = canon("outdoorandcountry")

from config import BARBOUR, BRAND_CONFIG, SETTINGS
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)


# ========== 浏览器与 Cookie ==========
def accept_cookies(driver, timeout=8):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except Exception:
        pass


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
    兼容 outdoorandcountry 新/旧 JSON-LD 结构:
    - offers[].mpn 有时是 "MWX0017NY9108"（最后2位是尺码）
    - 有时是 "MWX0017NY91"（直接是组合码）
    - 有时干脆是 "MWX0017NY91_08"
    你当前策略是：用颜色组合码，即 "MWX0017NY91" 这种 3+4+2+2 结构为佳。
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = script.string and script.string.strip()
            if not data:
                continue
            j = json.loads(data)
            if isinstance(j, dict) and j.get("@type") == "Product" and isinstance(j.get("offers"), list):
                for off in j["offers"]:
                    mpn = (off or {}).get("mpn")
                    if isinstance(mpn, str):
                        # 先尝试取 MWX0017NY91 这种完整组合码（截掉最后2位尺码）
                        if len(mpn) >= 11:
                            maybe_code = mpn[:-2]
                            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2}$", maybe_code):
                                return maybe_code
                        # 其次回退到末尾颜色块（OL99/NY91）
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
    return "男款"  # Outdoor 以男款为主，兜底男款


# ========== Outdoor 专属尺码逻辑 ==========
WOMEN_NUM = ["6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA = ["S", "M", "L", "XL", "XXL", "XXXL"]
MEN_NUM = [str(s) for s in range(32, 52, 2)]  # 32..50 偶数


def _clean_size(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    s = clean_size_for_barbour(raw) or raw
    return s.strip()


def _filter_and_sort_sizes(sizes, gender: str):
    """
    - 女款：统一映射为 6-20
    - 男款：字母 + 数字，过滤 52 及以上
    """
    gender = gender or ""
    sizes = [s for s in (sizes or []) if s]

    cleaned = []
    for s, status in sizes:
        val = _clean_size(s)
        if not val:
            continue
        cleaned.append((val, status))

    if not cleaned:
        return []

    # 按性别分支
    if gender == "女款":
        bucket = {}
        for s, status in cleaned:
            m = re.match(r"^(\d{1,2})$", s)
            if not m:
                continue
            num = int(m.group(1))
            if num < 6 or num > 20:
                continue
            bucket[num] = status
        ordered = []
        for num in WOMEN_NUM:
            n = int(num)
            if n in bucket:
                ordered.append((num, bucket[n]))
        return ordered

    # 男款 / 童款（童款也按男装数字字母混合处理）
    bucket = {}
    for s, status in cleaned:
        # 过滤 52 及以上
        m = re.match(r"^(\d{2})$", s)
        if m:
            num = int(m.group(1))
            if num >= 52:
                continue
            bucket[s] = status
        else:
            bucket[s] = status

    # 按字母优先 + 数字序次
    alpha_part = [(s, bucket[s]) for s in MEN_ALPHA if s in bucket]
    num_part = []
    for n in MEN_NUM:
        if n in bucket:
            num_part.append((n, bucket[n]))

    # 可能仍有残余码（比如 XS, XXL 之类），原顺序追加
    used = {s for s, _ in alpha_part + num_part}
    others = [(s, bucket[s]) for s in bucket if s not in used]

    return alpha_part + num_part + others


def _build_sizes_from_offers(offers, gender: str):
    """
    offers: [(size_str, price, stock_text, can_order), ...]
    输出：
      Product Size:        "6:有货;8:有货;10:无货;..."
      Product Size Detail: "6:3:0000000000000;8:0:0000000000000;..."
    """
    if not offers:
        return "No Data", "No Data"

    norm = []
    for size, price, stock_text, can_order in offers:
        size = (size or "").strip()
        stock = 0
        if (stock_text or "").strip().lower() in ("in stock", "available"):
            stock = DEFAULT_STOCK_COUNT
        if can_order and stock == 0:
            stock = DEFAULT_STOCK_COUNT
        norm.append((size, stock))

    # 统一清洗 + 过滤大尺码
    temp = []
    for size, stock in norm:
        cs = _clean_size(size)
        if not cs:
            continue
        # ⚠️ Outdoor 仅过滤 52 及以上
        m = re.match(r"^(\d{2})$", cs)
        if m and int(m.group(1)) >= 52:
            continue
        temp.append((cs, stock))

    if not temp:
        return "No Data", "No Data"

    # 按性别排序
    # 我们只关心是否有货 (>=1)，无货就记为 0
    bucket = {}
    for size, stock in temp:
        bucket[size] = max(bucket.get(size, 0), stock)

    # 性别映射
    g = gender or ""
    if "女" in g:
        chosen = WOMEN_NUM[:]
    else:
        # 男款/童款：字母+数字
        # 优先 MEN_ALPHA + MEN_NUM，最后 append 其它
        chosen = []
        for s in MEN_ALPHA:
            if s in bucket:
                chosen.append(s)
        for s in MEN_NUM:
            if s in bucket:
                chosen.append(s)
        # others
        for s in bucket:
            if s not in chosen:
                chosen.append(s)

    # 构建输出
    size_line = []
    detail = []
    for s in chosen:
        stock = bucket.get(s, 0)
        status = "有货" if stock > 0 else "无货"
        size_line.append(f"{s}:{status}")
        qty = DEFAULT_STOCK_COUNT if stock > 0 else 0
        detail.append(f"{s}:{qty}:0000000000000")

    if not size_line:
        return "No Data", "No Data"

    return ";".join(size_line), ";".join(detail)


def _fallback_style_category(name: str, desc: str, code: str) -> str:
    n = (name or "").lower()
    d = (desc or "").lower()
    c = (code or "").upper()

    def has(*words):
        return any(w in n or w in d for w in words)

    # 1) waxed jacket 兜底（关键）
    if ("wax" in n or "wax" in d) and ("jacket" in n or "coat" in n or "jacket" in d or "coat" in d):
        return "waxed jacket"
    if c.startswith("MWX") or c.startswith("LWX"):
        return "waxed jacket"

    # 2) quilted
    if has("quilt"):
        return "quilted jacket"

    # 3) gilet/bodywarmer
    if has("gilet", "bodywarmer", "vest"):
        return "gilet"

    # 4) knitwear
    if has("knit", "sweater", "jumper", "crew"):
        return "knitwear"

    # 5) shirt
    if has("shirt"):
        return "shirt"

    # 6) 通用 jacket
    if has("jacket", "coat", "parka"):
        return "jacket"

    return "No Data"


def _inject_price_from_offers(info: dict):
    """
    万一 parse_offer_info 没给原价/折扣价，就从 offers 兜底一个最小价格。
    """
    offers = info.get("Offers") or []
    prices = []
    for _, price, _, _ in offers:
        try:
            if price is None:
                continue
            prices.append(float(price))
        except Exception:
            continue

    if not prices:
        return

    # 最小价格兜底
    base = min(prices)
    info.setdefault("Product Price", base)
    info.setdefault("Adjusted Price", base)


def _clean_sizes(info: dict):
    """
    清洗 Product Size / Product Size Detail（如果存在的话）
    """
    gender = info.get("Product Gender") or ""
    # 当前实现只对 Detail 生效，Size 本身不再写（按你要求）
    detail = info.get("Product Size Detail")
    if not detail or detail == "No Data":
        return

    parts = []
    for item in str(detail).split(";"):
        item = item.strip()
        if not item:
            continue
        try:
            size, stock, ean = item.split(":")
        except ValueError:
            continue
        csize = _clean_size(size)
        if not csize:
            continue
        try:
            stock_val = int(stock)
        except Exception:
            stock_val = 0
        parts.append((csize, stock_val, ean))

    if not parts:
        return

    # 按性别排序（与上面 _filter_and_sort_sizes 一致）
    if "女" in gender:
        order = WOMEN_NUM
    else:
        order = MEN_ALPHA + MEN_NUM

    ordered = []
    used = set()
    for s in order:
        for size, stock, ean in parts:
            if size == s and size not in used:
                used.add(size)
                ordered.append((size, stock, ean))

    for size, stock, ean in parts:
        if size not in used:
            ordered.append((size, stock, ean))

    detail_line = []
    for size, stock, ean in ordered:
        detail_line.append(f"{size}:{stock}:{ean or '0000000000000'}")

    if detail_line:
        info["Product Size Detail"] = ";".join(detail_line)


def _ensure_detail_from_size(info: dict):
    """
    若无 Detail 但有 Size，则根据 Size 生成 Detail（有货=3，无货=0，EAN 占位）
    """
    if info.get("Product Size Detail") and info.get("Product Size Detail") != "No Data":
        return
    size = info.get("Product Size") or "No Data"
    if not size or size == "No Data":
        return

    detail = []
    for item in str(size).split(";"):
        item = item.strip()
        if not item:
            continue
        try:
            s, status = item.split(":")
        except ValueError:
            continue
        stock = DEFAULT_STOCK_COUNT if status == "有货" else 0
        detail.append(f"{s}:{stock}:0000000000000")
    if detail:
        info["Product Size Detail"] = ";".join(detail)


# ========== 主流程 ==========

# ========== 多线程 Chrome driver 管理（v2） ==========
# ========== 多线程 Chrome driver 管理（v3：改用 selenium_utils，仍然多线程） ==========
import threading
from common_taobao.core.selenium_utils import get_driver as _get_driver_v2
from common_taobao.core.selenium_utils import quit_all_drivers as _quit_all_drivers_v2

_thread_local_driver = threading.local()

def create_driver(headless: bool = False):
    # 仍然返回一个 driver；实际创建交给 selenium_utils
    # name 固定即可；selenium_utils 内部会自动带线程 id，确保每个线程一个 driver
    return _get_driver_v2(
        name="outdoorandcountry",
        headless=headless,
        window_size="1920,1080",
    )

def get_driver(headless: bool = False):
    driver = getattr(_thread_local_driver, "driver", None)
    if driver is None:
        driver = create_driver(headless=headless)
        _thread_local_driver.driver = driver
    return driver

def shutdown_all_drivers():
    # 关闭所有线程的 driver
    _quit_all_drivers_v2()


def process_url(url, output_dir):
    
    try:
        driver = get_driver()
        print(f"\n🌐 正在抓取: {url}")
        driver.get(url)
        accept_cookies(driver)
        time.sleep(3)
        html = driver.page_source

        # 1) 解析（复用你已有的站点解析）
        info = parse_offer_info(html, url, site_name=CANON_SITE) or {}
        url_color = _normalize_color_from_url(url)

        if info.get("original_price_gbp"):
            info["Product Price"] = info["original_price_gbp"]
        if info.get("discount_price_gbp"):
            info["Adjusted Price"] = info["discount_price_gbp"]
        # 2) 基础字段补齐（统一）
        info.setdefault("Brand", "Barbour")
        info.setdefault("Product Name", "No Data")
        info.setdefault("Product Color", url_color or "No Data")
        info.setdefault("Product Description", _extract_description(html))
        info.setdefault("Feature", _extract_features(html))
        info.setdefault("Site Name", CANON_SITE)
        info["Source URL"] = url  # 与其他站点保持一致的字段名

        # 3) Product Code / Product Color Code（你的策略：组合码即可）
        color_code = info.get("Product Color Code") or _extract_color_code_from_jsonld(html)
        if color_code:
            info["Product Color Code"] = color_code
            info["Product Code"] = color_code  # ✅ 你要求：直接把组合码当 Product Code

        # 4) 性别（优先标题/名称关键词，兜底男款）
        if not info.get("Product Gender"):
            info["Product Gender"] = _infer_gender_from_name(info.get("Product Name", ""))

        # 5) Offers → 两行尺码（不写 SizeMap，且过滤 52）
        offers = info.get("Offers") or []
        # ⚠️ 按你的要求：不再写入 Product Size，只保留 Detail
        _, psd = _build_sizes_from_offers(offers, info["Product Gender"])
        info["Product Size Detail"] = psd

        # 6) 类目（本地兜底，防止 category_utils 旧版误判）
        if not info.get("Style Category"):
            info["Style Category"] = _fallback_style_category(
                info.get("Product Name", ""),
                info.get("Product Description", ""),
                info.get("Product Code", "") or ""
            )

        # ========= ✅ Outdoor 专属增强：写盘前一次性处理 =========
        _inject_price_from_offers(info)   # Outdoor 无价 → 从 offers 补
        _clean_sizes(info)                # 清洗（仅 Detail 生效）
        _ensure_detail_from_size(info)    # 没 Detail 就从 Size 兜底（Detail 用 3/0）

        # 7) 文件名策略
        if color_code:
            filename = f"{sanitize_filename(color_code)}.txt"
        else:
            safe_name = sanitize_filename(info.get('Product Name', 'NoName'))
            safe_color = sanitize_filename(info.get('Product Color', 'NoColor'))
            filename = f"{safe_name}_{safe_color}.txt"

        # 8) ✅ 统一用 txt_writer.format_txt 写出（与其它站点完全一致）
        output_dir.mkdir(parents=True, exist_ok=True)
        txt_path = output_dir / filename
        format_txt(info, txt_path, brand="Barbour")
        print(f"✅ 写入: {txt_path.name}")

    except Exception as e:
        print(f"❌ 处理失败: {url}\n    {e}")


def outdoorandcountry_fetch_info(max_workers=3):
    links_file = BARBOUR["LINKS_FILES"]["outdoorandcountry"]
    output_dir = BARBOUR["TXT_DIRS"]["outdoorandcountry"]
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = []
    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                urls.append(url)

    print(f"🔄 启动多线程抓取，总链接数: {len(urls)}，并发线程数: {max_workers}")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_url, url, output_dir) for url in urls]
            for fut in as_completed(futures):
                fut.result()
    finally:
        shutdown_all_drivers()


if __name__ == "__main__":
    outdoorandcountry_fetch_info(max_workers=3)
