# brands/barbour/supplier/cho_fetch_info.py
# -*- coding: utf-8 -*-

"""
CHO | Barbour 商品抓取脚本
- 解析 Shopify JSON-LD ProductGroup + DOM 价格区
- TXT 输出模板与 Outdoor / Allweathers 完全一致（使用 format_txt）
"""

import re
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

from bs4 import BeautifulSoup
from selenium import webdriver

import demjson3

from brands.barbour.core.site_utils import assert_site_or_raise as canon

# 统一 TXT 写入
from common_taobao.ingest.txt_writer import format_txt
from config import BARBOUR, BRAND_CONFIG, SETTINGS
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)
# 可选 stealth
try:
    from selenium_stealth import stealth
except ImportError:
    def stealth(*args, **kwargs):
        return

# 可选：Barbour 性别修正（根据编码前缀等）
try:
    from common_taobao.core.size_normalizer import infer_gender_for_barbour
except Exception:
    infer_gender_for_barbour = None

# ========== 全局配置 ==========

CANON_SITE = canon("cho")  # 确保在 site_utils 里有映射
LINK_FILE = BARBOUR["LINKS_FILES"]["cho"]
TXT_DIR = BARBOUR["TXT_DIRS"]["cho"]
TXT_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 4


# ========== Selenium Driver ==========

def get_driver():
    """
    简单版 driver；如果你后面统一改成 selenium_utils，这里直接替换即可。
    """
    temp_profile = tempfile.mkdtemp()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"--user-data-dir={temp_profile}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    try:
        stealth(
            driver,
            languages=["en-GB", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    except Exception:
        # 没有 stealth 也不影响
        pass
    return driver


# ========== 工具函数（与 Allweathers 同风格） ==========

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _infer_gender_from_title(title_or_name: str) -> str:
    t = (title_or_name or "").lower()
    if re.search(r"\b(women|woman|women's|ladies)\b", t):
        return "女款"
    if re.search(r"\b(men|men's|man)\b", t):
        return "男款"
    if re.search(r"\b(kids?|boys?|girls?)\b", t):
        return "童款"
    return "未知"


def _to_float(x: str) -> float | None:
    if not x:
        return None
    try:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", x.replace(",", ""))
        return float(m.group(1)) if m else None
    except Exception:
        return None


def _extract_price_pair_from_dom_cho(soup: BeautifulSoup) -> Tuple[float | None, float | None]:
    """
    从 CHO DOM 中抓取 (original_price, current_price)
    - 打折时：
        .price__sale .price-item--sale        => 现价
        .savings-price .price-item--regular   => 原价
    - 无打折：
        .price__regular .price-item--regular  => 原价 == 现价
    """
    # 有打折
    sale_span = soup.select_one(".price__sale .price-item--sale")
    was_span = soup.select_one(".price__sale .savings-price .price-item--regular")
    sale_price = _to_float(sale_span.get_text(" ", strip=True)) if sale_span else None
    was_price = _to_float(was_span.get_text(" ", strip=True)) if was_span else None

    if sale_price is not None and was_price is not None:
        return was_price, sale_price  # (原价, 折后价)

    # 无打折 → 直接用 regular 价
    reg_span = soup.select_one(".price__regular .price-item--regular")
    reg_price = _to_float(reg_span.get_text(" ", strip=True)) if reg_span else None
    if reg_price is not None:
        return reg_price, reg_price

    return None, None


def _load_product_jsonld(soup: BeautifulSoup) -> dict:
    """
    返回 JSON-LD 中的 ProductGroup / Product 节点（CHO 用 ProductGroup）
    """
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        txt = (tag.string or tag.text or "").strip()
        if not txt:
            continue
        try:
            j = demjson3.decode(txt)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            return j
    raise ValueError("未找到 ProductGroup/Product JSON-LD 数据")


def _extract_code_from_description(desc: str) -> str:
    """
    从 description 末尾提取 Barbour 编码，如 MQU0281NY71。
    一般在最后一行。
    """
    if not desc:
        return "No Data"
    # 先按行拆分，取最后一个非空行
    lines = [l.strip() for l in desc.splitlines() if l.strip()]
    if lines:
        last = lines[-1]
        m = re.search(r"\b[A-Z0-9]{3}\d{4}[A-Z0-9]{2}\d{2}\b", last)
        if m:
            return m.group(0)

    # 全文兜底：取最后一个匹配
    m_all = list(re.finditer(r"\b[A-Z0-9]{3}\d{4}[A-Z0-9]{2}\d{2}\b", desc))
    if m_all:
        return m_all[-1].group(0)
    return "No Data"


def _strip_code_from_description(desc: str, code: str) -> str:
    if not desc:
        return "No Data"
    if not code or code == "No Data":
        return _clean_text(desc)
    return _clean_text(desc.replace(code, "")).strip(" -–|,")


# ========== 尺码处理（直接复用 Allweathers 逻辑） ==========

WOMEN_ORDER = ["4", "6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA_ORDER = ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（不含52）

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS",  "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}


def _choose_full_order_for_gender(gender: str, present: set[str]) -> list[str]:
    """与 Allweathers 保持一致：男款在【字母系】与【数字系】二选一；女款固定 4–20。"""
    g = (gender or "").lower()
    if "女" in g:
        return WOMEN_ORDER[:]

    has_num = any(k in MEN_NUM_ORDER for k in present)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in present)
    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]
    if has_num or has_alpha:
        num_count = sum(1 for k in present if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in present if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]
    return MEN_ALPHA_ORDER[:]


def _normalize_size(token: str, gender: str) -> str | None:
    """
    与 Allweathers 一致的归一化逻辑：
    - 女款：4–20 数字
    - 男款：30–50 偶数 或 2XS..3XL
    """
    s = (token or "").strip().upper()
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)
    s = re.sub(r"\s+", " ", s)

    # 数字优先
    m = re.findall(r"\d{1,3}", s)
    if m:
        n = int(m[0])
        if gender == "女款" and n in {4, 6, 8, 10, 12, 14, 16, 18, 20}:
            return str(n)
        if gender == "男款":
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)
            if 28 <= n <= 54:
                cand = n if n % 2 == 0 else n - 1
                cand = max(30, min(50, cand))
                return str(cand)
        return None

    key = s.replace("-", "").replace(" ", "")
    return ALPHA_MAP.get(key)


def _build_size_lines_from_sizedetail(size_detail: dict, gender: str) -> tuple[str, str]:
    """
    输入：SizeDetail = { raw_size: {stock_count:int, ean:str}, ... }
    输出：
      Product Size        = "M:有货;L:无货;..."
      Product Size Detail = "M:3:000...;L:0:000...;..."
    """
    bucket_status: dict[str, str] = {}
    bucket_stock: dict[str, int] = {}

    # 1) 汇总页面出现的尺码
    for raw_size, meta in (size_detail or {}).items():
        norm = _normalize_size(raw_size, gender or "男款")
        if not norm:
            continue
        stock = int(meta.get("stock_count", 0) or 0)
        status = "有货" if stock > 0 else "无货"
        prev = bucket_status.get(norm)
        if prev is None or (prev == "无货" and status == "有货"):
            bucket_status[norm] = status
            bucket_stock[norm] = DEFAULT_STOCK_COUNT if stock > 0 else 0

    # 2) 选择单一尺码系
    present_keys = set(bucket_status.keys())
    full_order = _choose_full_order_for_gender(gender or "男款", present_keys)

    # 2.5) 清除不在该体系内的尺码
    for k in list(bucket_status.keys()):
        if k not in full_order:
            bucket_status.pop(k, None)
            bucket_stock.pop(k, None)

    # 3) 补齐未出现的尺码为无货/0
    for size in full_order:
        if size not in bucket_status:
            bucket_status[size] = "无货"
            bucket_stock[size] = 0

    ordered = list(full_order)
    ps = ";".join(f"{k}:{bucket_status[k]}" for k in ordered)
    psd = ";".join(f"{k}:{bucket_stock[k]}:0000000000000" for k in ordered)
    return ps, psd


# ========== 解析详情页 ==========

def parse_detail_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    data = _load_product_jsonld(soup)
    name = data.get("name") or (soup.title.get_text(strip=True) if soup.title else "No Data")
    desc = data.get("description") or ""
    desc = desc.replace("\\n", "\n")
    desc = desc.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

    product_code = _extract_code_from_description(desc)
    description = _strip_code_from_description(desc, product_code)

    # 尺码/库存
    variants = data.get("hasVariant", [])
    if isinstance(variants, dict):
        variants = [variants]
    if not variants:
        raise ValueError("未找到 hasVariant 变体数据")

    size_detail = {}
    color = "No Data"

    for v in variants:
        v_name = v.get("name") or ""
        # name 形如：Barbour Powell Mens Quilted Jacket - Navy - Navy / L
        tail = v_name.split(" - ")[-1] if " - " in v_name else v_name
        if " / " in tail:
            c_txt, sz_txt = [p.strip() for p in tail.split(" / ", 1)]
        else:
            c_txt, sz_txt = (tail.strip() or "No Data"), "Unknown"
        if color == "No Data":
            color = c_txt or "No Data"

        offers = v.get("offers") or {}
        avail = (offers.get("availability") or "").lower()
        in_stock = "instock" in avail

        size_detail[sz_txt] = {
            "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
            "ean": v.get("gtin") or v.get("sku") or "0000000000000",
        }

    gender_guess = _infer_gender_from_title(name)

    # 价格：DOM 优先（原价/折后价）
    original_price, current_price = _extract_price_pair_from_dom_cho(soup)

    info = {
        "Product Code": product_code or "No Data",
        "Product Name": name,
        "Product Description": description or "No Data",
        "Product Gender": gender_guess,
        "Product Color": color or "No Data",
        "Product Price": original_price,
        "Adjusted Price": current_price,
        "Product Material": "No Data",
        "Feature": "No Data",
        "SizeDetail": size_detail,
        "Source URL": url,
        "Site Name": CANON_SITE,
    }
    return info


# ========== 抓取 & 写 TXT ==========

def fetch_one_product(url: str, idx: int, total: int):
    print(f"[{idx}/{total}] 抓取: {url}")
    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(2.5)
        html = driver.page_source
        driver.quit()

        info = parse_detail_page(html, url)

        # 基础字段补齐
        info.setdefault("Brand", "Barbour")
        info.setdefault("Site Name", CANON_SITE)
        info.setdefault("Source URL", url)

        # 性别修正：优先根据 Barbour 编码
        if infer_gender_for_barbour:
            info["Product Gender"] = infer_gender_for_barbour(
                product_code=info.get("Product Code"),
                title=info.get("Product Name"),
                description=info.get("Product Description"),
                given_gender=info.get("Product Gender"),
            ) or info.get("Product Gender") or "男款"

        # SizeDetail → Product Size / Product Size Detail
        if info.get("SizeDetail") and (not info.get("Product Size") or not info.get("Product Size Detail")):
            ps, psd = _build_size_lines_from_sizedetail(info["SizeDetail"], info.get("Product Gender", "男款"))
            info["Product Size"] = info.get("Product Size") or ps
            info["Product Size Detail"] = info.get("Product Size Detail") or psd

        # 文件名：使用 Product Code
        code = info.get("Product Code") or "NoData"
        safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", code)
        txt_path = TXT_DIR / f"{safe_code}.txt"

        format_txt(info, txt_path, brand="Barbour")
        return (url, "✅ 成功")
    except Exception as e:
        return (url, f"❌ 失败: {e}")


def cho_fetch_info(max_workers: int = MAX_WORKERS):
    print(f"🚀 启动 CHO 多线程商品详情抓取（线程数: {max_workers}）")
    links = LINK_FILE.read_text(encoding="utf-8").splitlines()
    links = [u.strip() for u in links if u.strip()]
    total = len(links)
    if total == 0:
        print("⚠ 链接文件为空")
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(fetch_one_product, url, idx + 1, total)
            for idx, url in enumerate(links)
        ]
        for future in as_completed(futures):
            url, status = future.result()
            print(f"{status} - {url}")

    print("\n✅ CHO 商品抓取完成")


if __name__ == "__main__":
    cho_fetch_info(max_workers=10)
