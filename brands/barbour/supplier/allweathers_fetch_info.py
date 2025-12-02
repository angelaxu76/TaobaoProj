# barbour/supplier/allweathers_fetch_info.py
# -*- coding: utf-8 -*-

import re
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import demjson3
from bs4 import BeautifulSoup
from selenium import webdriver

from config import BARBOUR, SETTINGS
from brands.barbour.core.site_utils import assert_site_or_raise as canon
from common_taobao.core.selenium_utils import get_driver as shared_get_driver, quit_driver

# ✅ 统一写入：使用你的 txt_writer，保证与其它站点同模板
from common_taobao.ingest.txt_writer import format_txt  # 与项目当前用法保持一致

# 可选的 selenium_stealth（无则跳过）
try:
    from selenium_stealth import stealth
except ImportError:
    def stealth(*args, **kwargs):
        return

# —— 新增：性别修正（Barbour 编码前缀优先）——
try:
    from common_taobao.core.size_normalizer import infer_gender_for_barbour
except Exception:
    infer_gender_for_barbour = None  # 若未提供共享模块，下面会用本地兜底

# -------- 全局配置 --------
CANON_SITE = canon("allweathers")  # 这里是注释，不要写成（= "allweathers"）
LINK_FILE = BARBOUR["LINKS_FILES"]["allweathers"]
TXT_DIR = BARBOUR["TXT_DIRS"]["allweathers"]
TXT_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 6

DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)
# ============ 抽取辅助函数（与户外站实际页面适配） ============

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


def _extract_name_and_color(soup: BeautifulSoup) -> tuple[str, str]:
    # 优先 og:title：形如 "Barbour Acorn Women's Waxed Jacket | Olive"
    og = soup.find("meta", {"property": "og:title"})
    if og and og.get("content"):
        txt = og["content"].strip()
        if "|" in txt:
            name, color = map(str.strip, txt.split("|", 1))
            return name, color
        return txt, "Unknown"

    # 其次 document.title
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        t = t.split("|", 1)[0].strip()
        if "–" in t:
            name, color = map(str.strip, t.split("–", 1))
            return name, color
        return t, "Unknown"

    return "Unknown", "Unknown"


def _extract_description(soup: BeautifulSoup) -> str:
    # 1) twitter:description
    m = soup.find("meta", attrs={"name": "twitter:description"})
    if m and m.get("content"):
        desc = _clean_text(m["content"])
        # 去掉 “Key Features …” 等尾注
        desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
        return desc

    # 2) og:description
    m = soup.find("meta", attrs={"property": "og:description"})
    if m and m.get("content"):
        return _clean_text(m["content"])

    # 3) JSON-LD ProductGroup.description
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = _clean_text(j.get("description") or "")
            if desc:
                desc = re.split(r"(Key\s*Features|Materials\s*&\s*Technical)", desc, flags=re.I)[0].strip(" -–|,")
                return desc
    return "No Data"


def _extract_features(soup: BeautifulSoup) -> str:
    # 寻找 “Key Features & Benefits” 标题后的列表
    h = soup.find(["h2", "h3"], string=re.compile(r"Key\s*Features", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            items = []
            for li in ul.find_all("li"):
                txt = _clean_text(li.get_text(" ", strip=True))
                if txt:
                    items.append(txt)
            if items:
                return " | ".join(items)

    # 退回 JSON-LD description 里的 “Key Features …（到 Materials 之前）”
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            if "Key" in desc:
                m = re.search(
                    r"Key\s*Features.*?:\s*(.+?)\s*(Materials\s*&\s*Technical|Frequently|$)",
                    desc, flags=re.I | re.S
                )
                if m:
                    block = m.group(1)
                    parts = [_clean_text(p) for p in re.split(r"[\r\n]+|•|- ", block)]
                    parts = [p for p in parts if p]
                    if parts:
                        return " | ".join(parts)
    return "No Data"


def _extract_material_outer(soup: BeautifulSoup) -> str:
    # 页面 H2 “Materials & Technical Specifications” 列表中的 Outer
    h = soup.find(["h2", "h3"], string=re.compile(r"Materials\s*&\s*Technical", re.I))
    if h:
        ul = h.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                txt = _clean_text(li.get_text(" ", strip=True))
                m = re.match(r"Outer:\s*(.+)", txt, flags=re.I)
                if m:
                    return m.group(1)

    # 退回 JSON-LD description
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            j = demjson3.decode(s.string)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") in ("ProductGroup", "Product"):
            desc = j.get("description") or ""
            m = re.search(r"Outer:\s*(.+)", desc, flags=re.I)
            if m:
                outer_line = _clean_text(m.group(1))
                outer_line = re.split(r"[\r\n;]+", outer_line)[0].strip()
                return outer_line
    return "No Data"


def _extract_header_price(soup: BeautifulSoup) -> float | None:
    # Shopify 常见的 meta 价格
    m = soup.find("meta", {"property": "product:price:amount"})
    if m and m.get("content"):
        try:
            return float(m["content"])
        except Exception:
            pass
    return None

# —— 新增：从主商品区成对抽取（原价/现价） —— 
def _extract_price_pair_from_dom(soup: BeautifulSoup):
    """
    返回 (original_price, current_price)。
    仅从主商品块 <price-list class="price-list--product"> 里抓：
      <sale-price>£现价</sale-price>
      <compare-at-price>£原价</compare-at-price>
    若取不到，返回 (None, None) 交给上层用 _extract_header_price 兜底。
    """
    block = soup.find("price-list", class_=re.compile(r"\bprice-list--product\b"))
    if not block:
        return (None, None)

    def _to_float(x: str):
        try:
            return float(re.search(r"([0-9]+(?:\.[0-9]+)?)", x.replace(",", "")).group(1))
        except Exception:
            return None

    sale_el = block.find("sale-price")
    comp_el = block.find("compare-at-price")
    sale = _to_float(sale_el.get_text(" ", strip=True)) if sale_el else None
    comp = _to_float(comp_el.get_text(" ", strip=True)) if comp_el else None

    if sale and comp:
        return (comp, sale)           # (原价, 现价)
    if sale and not comp:
        return (sale, sale)           # 无原价节点 → 视为无折扣
    if comp and not sale:
        return (comp, comp)           # 极少数主题写反 → 兜底
    return (None, None)

# ============ 解析详情页为统一 info（爬取逻辑保持不变） ============

def parse_detail_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # 名称 & 颜色
    name, color = _extract_name_and_color(soup)

    # JSON-LD（Shopify ProductGroup）
    script = soup.find("script", {"type": "application/ld+json"})
    if not script:
        raise ValueError("未找到 JSON-LD 数据段")

    data = demjson3.decode(script.string)
    variants = data.get("hasVariant", []) if isinstance(data, dict) else []
    if not variants:
        raise ValueError("❌ 未找到尺码变体")

    # 商品编码（色码含在编码末尾）：如 LWX0752OL51-16 → LWX0752OL51
    first_sku = (variants[0].get("sku") or "")
    base_sku = first_sku.split("-")[0] if first_sku else "Unknown"

    # 尺码/价格/库存
    size_detail = {}
    for item in variants:
        sku = item.get("sku", "")
        offer = item.get("offers") or {}
        try:
            price = float(offer.get("price", 0.0))
        except Exception:
            price = 0.0
        availability = (offer.get("availability") or "").lower()
        can_order = "instock" in availability
        # UK 尺码在 sku 尾部：LWX0752OL51-16 → UK 16
        size_tail = sku.split("-")[-1] if "-" in sku else "Unknown"
        size = f"UK {re.sub(r'\\s+', ' ', size_tail)}"
        size_detail[size] = {
            "stock_count": DEFAULT_STOCK_COUNT if can_order else 0,  # 统一上架量策略
            "ean": "0000000000000",                # 占位 EAN
        }

    gender = _infer_gender_from_title(name)
    description = _extract_description(soup)
    features = _extract_features(soup)
    material_outer = _extract_material_outer(soup)
    # 价格：优先 DOM 成对价；缺失则回退 header（现价）
    price_header = _extract_header_price(soup)  # 常等于现价
    orig, curr = _extract_price_pair_from_dom(soup)
    original_price = orig or price_header
    current_price = curr or price_header



    info = {
        "Product Code": base_sku,
        "Product Name": name,
        "Product Description": description,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": original_price,   # ✅ 原价
        "Adjusted Price": current_price,   # ✅ 现价/折后价
        "Product Material": material_outer,
        # "Style Category": 留空让写入器自动 infer（如你已升级分类器）
        "Feature": features,
        "SizeDetail": size_detail,       # 每码库存/占位 EAN（写入前再转两行）
        "Source URL": url,
        "Site Name": CANON_SITE,
    }
    return info


# ============ 后处理（不改爬取，只整理写入字段） ============

WOMEN_ORDER = ["4","6","8","10","12","14","16","18","20"]
MEN_ALPHA_ORDER = ["2XS","XS","S","M","L","XL","2XL","3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50（按你要求：不包含 52）

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}

def _choose_full_order_for_gender(gender: str, present: set[str]) -> list[str]:
    """男款在【字母系】与【数字系】二选一；女款固定 4–20。"""
    g = (gender or "").lower()
    if "女" in g:
        return WOMEN_ORDER[:]  # 4..20

    has_num   = any(k in MEN_NUM_ORDER   for k in present)
    has_alpha = any(k in MEN_ALPHA_ORDER for k in present)
    if has_num and not has_alpha:
        return MEN_NUM_ORDER[:]          # 30..50（不含52）
    if has_alpha and not has_num:
        return MEN_ALPHA_ORDER[:]        # 2XS..3XL
    if has_num or has_alpha:
        num_count   = sum(1 for k in present if k in MEN_NUM_ORDER)
        alpha_count = sum(1 for k in present if k in MEN_ALPHA_ORDER)
        return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]
    # 实在判不出来，默认用字母系
    return MEN_ALPHA_ORDER[:]


def _normalize_size(token: str, gender: str) -> str | None:
    """将 'UK 36' / '36' / 'XL' 归一到你的标准，并过滤男款 52。"""
    s = (token or "").strip().upper()
    s = s.replace("UK ", "").replace("EU ", "").replace("US ", "")
    s = re.sub(r"\s*\(.*?\)\s*", "", s)
    s = re.sub(r"\s+", " ", s)

    # 先数字
    m = re.findall(r"\d{1,3}", s)
    if m:
        n = int(m[0])
        if gender == "女款" and n in {4,6,8,10,12,14,16,18,20}:
            return str(n)
        if gender == "男款":
            # 男数字：30..50（偶数），且显式排除 52
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)
            # 容错贴近：对 28..54 取就近偶数并裁剪到 30..50
            if 28 <= n <= 54:
                cand = n if n % 2 == 0 else n-1
                cand = max(30, min(50, cand))
                return str(cand)
        # 其它场景：不返回
        return None

    # 再字母
    key = s.replace("-", "").replace(" ", "")
    return ALPHA_MAP.get(key)

def _sort_sizes(keys: list[str], gender: str) -> list[str]:
    if gender == "女款":
        return [k for k in WOMEN_ORDER if k in keys]
    # 男款：字母优先，再数字
    ordered = [k for k in MEN_ALPHA_ORDER if k in keys] + [k for k in MEN_NUM_ORDER if k in keys]
    return ordered

def _build_size_lines_from_sizedetail(size_detail: dict, gender: str) -> tuple[str, str]:
    bucket_status: dict[str, str] = {}
    bucket_stock: dict[str, int] = {}

    # 1) 汇总页面出现的尺码（有货优先）
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

    # 2) 选择“单一尺码系”的完整顺序表（男款二选一；女款固定）
    present_keys = set(bucket_status.keys())
    full_order = _choose_full_order_for_gender(gender or "男款", present_keys)

    # ★★★ 2.5) 先把“另一套系”的键清掉（防止后续被下游再拼回去）
    for k in list(bucket_status.keys()):
        if k not in full_order:
            bucket_status.pop(k, None)
            bucket_stock.pop(k, None)

    # 3) 仅在选定那一系内补齐未出现的尺码为 0
    for size in full_order:
        if size not in bucket_status:
            bucket_status[size] = "无货"
            bucket_stock[size] = 0

    # 4) 按选定系固定顺序输出
    ordered = list(full_order)
    ps  = ";".join(f"{k}:{bucket_status[k]}" for k in ordered)
    psd = ";".join(f"{k}:{bucket_stock[k]}:0000000000000" for k in ordered)
    return ps, psd


# ============ 抓取并写入 TXT（pipeline 签名保持不变） ============

def fetch_one_product(url: str, idx: int, total: int):
    print(f"[{idx}/{total}] 抓取: {url}")
    driver_name = f"allweathers_{idx}"    # 每个任务单独一个 driver 名

    try:
        driver = shared_get_driver(
            name=driver_name,
            headless=True,
            window_size="1920,1080",
        )
        driver.get(url)
        time.sleep(2.5)
        html = driver.page_source

        # —— 不改爬取逻辑：保留你原有的解析 ——
        info = parse_detail_page(html, url)

        # —— 写入前的规范化：只做字段清洗，不触碰抓取流程 ——
        # 品牌与站点信息
        info.setdefault("Brand", "Barbour")
        info.setdefault("Site Name", CANON_SITE)
        info.setdefault("Source URL", url)

        # 性别修正（优先 Barbour 编码前缀；再看标题/描述；否则用原值）
        if infer_gender_for_barbour:
            info["Product Gender"] = infer_gender_for_barbour(
                product_code=info.get("Product Code"),
                title=info.get("Product Name"),
                description=info.get("Product Description"),
                given_gender=info.get("Product Gender"),
            ) or info.get("Product Gender") or "男款"

        # 由 SizeDetail 生成两行（不输出 SizeMap；并过滤男款 52）
        if info.get("SizeDetail") and (not info.get("Product Size") or not info.get("Product Size Detail")):
            ps, psd = _build_size_lines_from_sizedetail(info["SizeDetail"], info.get("Product Gender", "男款"))
            info["Product Size"] = info.get("Product Size") or ps
            info["Product Size Detail"] = info.get("Product Size Detail") or psd

        # 文件名：用 Product Code
        code = info.get("Product Code") or "Unknown"
        safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", code)
        txt_path = TXT_DIR / f"{safe_code}.txt"

        # ✅ 统一写入（同其它站点）
        format_txt(info, txt_path, brand="Barbour")
        return (url, "✅ 成功")
    except Exception as e:
        return (url, f"❌ 失败: {e}")
    finally:
        quit_driver(driver_name)


def allweathers_fetch_info(max_workers: int = MAX_WORKERS):
    print(f"🚀 启动 Allweathers 多线程商品详情抓取（线程数: {max_workers}）")
    links = LINK_FILE.read_text(encoding="utf-8").splitlines()
    links = [u.strip() for u in links if u.strip()]
    total = len(links)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(fetch_one_product, url, idx + 1, total)
            for idx, url in enumerate(links)
        ]
        for future in as_completed(futures):
            url, status = future.result()
            print(f"{status} - {url}")

    print("\n✅ 所有商品抓取完成")


if __name__ == "__main__":
    allweathers_fetch_info()
