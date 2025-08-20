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
5) ✅ 新增（仅在本模块内完成的业务处理，不侵入 writer/parser）：
   - 从 Offers 回填 Product Price（有货优先）
   - 对 Product Size / Product Size Detail 的尺码做清洗
   - 若无 Product Size Detail，按 Size 兜底生成（有货=1/无货=0，EAN 占位）
"""

import time
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote

import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from config import BARBOUR
from barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# ✅ 统一 TXT 写入（与其它站点一致）
from common_taobao.txt_writer import format_txt

# ✅ 尺码清洗（保守：识别不了就原样返回）
from common_taobao.size_utils import clean_size_for_barbour  # 见你上传的实现

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
    return re.sub(r"[\\/:*?\"<>|'\s]+", "_", (name or "").strip())

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
            if items:
                return " | ".join(items)
    return "No Data"

def _extract_color_code_from_jsonld(html: str) -> str:
    """
    从 JSON-LD 的 offers[].mpn 提取颜色编码（或组合码）。例如：
    mpn: MWX0017NY9140 -> 颜色位 NY91（你当前逻辑把 MWX0017NY91 当 product code 使用也可以）
    这里按你现有正则，提取 NY99/NY91 这类；如果站点给的是完整 MWX0017NY91 也会传递回去。
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
                            # 简单校验：前三位字母 + 数字 + 两位字母两位数字
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
    if any(x in n for x in ["kid", "kids", "child", "children", "boys", "girls", "boy's", "girl's", "junior", "youth"]):
        return "童款"
    return "男款"  # 兜底按男款

def _fallback_style_category(name: str, desc: str, product_code: str) -> str:
    """
    本地兜底：即使你的 category_utils 还是鞋类版，也不会把外套误判。
    """
    text = f"{name} {desc}".lower()
    if ("wax" in text and "jacket" in text) or (product_code[:3] in {"MWX", "LWX"}):
        return "waxed jacket"
    if "quilt" in text and "jacket" in text or (product_code[:3] in {"MQU", "LQU"}):
        return "quilted jacket"
    return "casual wear"

def _build_sizes_from_offers(offers, gender: str):
    """
    不依赖公共 size_normalizer，按你的新规则生成两行：
    - Product Size（不含 52，也不含 >50 的数字尺码）
    - Product Size Detail（同上）
    说明：你明确不要 SizeMap，就不返回它。
    """
    # 归一 + 过滤
    def norm(raw):
        s = (raw or "").strip().upper().replace("UK ", "")
        s = re.sub(r"\s*\(.*?\)\s*", "", s)
        # 数字抽取优先
        m = re.findall(r"\d{2,3}", s)
        if m:
            n = int(m[0])
            # 女：4..20（偶数）
            if 4 <= n <= 20 and n % 2 == 0 and gender == "女款":
                return str(n)
            # 男数字：30..50（偶数），且你要求不要 52
            if 30 <= n <= 50 and n % 2 == 0 and gender == "男款":
                return str(n)
            # 其它情况：尝试靠近就近偶数
            if gender == "男款" and 28 <= n <= 54:
                candidate = n if n % 2 == 0 else n-1
                candidate = max(30, min(50, candidate))
                return str(candidate)
        # 字母尺码
        map_alpha = {
            "XXXS":"2XS","2XS":"2XS","XXS":"XS","XS":"XS",
            "S":"S","SMALL":"S","M":"M","MEDIUM":"M","L":"L","LARGE":"L",
            "XL":"XL","X-LARGE":"XL","XXL":"2XL","2XL":"2XL","XXXL":"3XL","3XL":"3XL"
        }
        key = s.replace("-", "").replace(" ", "")
        return map_alpha.get(key)

    bucket = {}
    for size, price, stock_text, can_order in offers or []:
        ns = norm(size)
        if not ns:
            continue
        # 有货优先覆盖
        curr = "有货" if bool(can_order) else "无货"
        prev = bucket.get(ns)
        if prev is None or (prev == "无货" and curr == "有货"):
            bucket[ns] = curr

    # 排序：女 4..20；男 字母→数字（30..50）；不输出 52
    WOMEN = ["4","6","8","10","12","14","16","18","20"]
    MEN_ALPHA = ["2XS","XS","S","M","L","XL","2XL","3XL"]
    MEN_NUM = [str(n) for n in range(30, 52, 2)]  # 30..50

    ordered = []
    if gender == "女款":
        ordered = [k for k in WOMEN if k in bucket]
    else:
        ordered = [k for k in MEN_ALPHA if k in bucket] + [k for k in MEN_NUM if k in bucket]

    product_size = ";".join(f"{k}:{bucket[k]}" for k in ordered)
    product_size_detail = ";".join(f"{k}:{1 if bucket[k]=='有货' else 0}:0000000000000" for k in ordered)
    return product_size, product_size_detail

# ========= 新增：仅在本模块内做的 Outdoor 专属业务处理 =========
def _inject_price_from_offers(info: dict) -> None:
    """Outdoor 页无显式价格时，从 Offers 回填（有货优先，其次第一条）"""
    if info.get("Product Price"):
        return
    offers = info.get("Offers") or []
    price_val = None
    for size, price, stock_text, can_order in offers:
        if price:
            if can_order:              # 有货价优先
                price_val = price
                break
            if price_val is None:      # 否则先记第一条
                price_val = price
    if price_val:
        info["Product Price"] = str(price_val)

def _clean_sizes(info: dict) -> None:
    """对两行尺码做一次清洗；不识别则保持原样"""
    # Product Size: "S:有货;M:无货..."
    if info.get("Product Size"):
        cleaned = []
        for token in str(info["Product Size"]).split(";"):
            token = token.strip()
            if not token:
                continue
            try:
                size, status = token.split(":")
                size = clean_size_for_barbour(size)
                cleaned.append(f"{size}:{status}")
            except ValueError:
                cleaned.append(token)
        info["Product Size"] = ";".join(cleaned)

    # Product Size Detail: "S:1:EAN;M:0:EAN..."
    if info.get("Product Size Detail"):
        cleaned = []
        for token in str(info["Product Size Detail"]).split(";"):
            token = token.strip()
            if not token:
                continue
            parts = token.split(":")
            if len(parts) == 3:
                size, stock, ean = parts
                size = clean_size_for_barbour(size)
                cleaned.append(f"{size}:{stock}:{ean}")
            else:
                cleaned.append(token)
        info["Product Size Detail"] = ";".join(cleaned)

def _ensure_detail_from_size(info: dict) -> None:
    """若无 Detail，用 Size 兜底生成（有货=1，无货=0，EAN 占位）"""
    if info.get("Product Size") and not info.get("Product Size Detail"):
        detail = []
        for token in str(info["Product Size"]).split(";"):
            token = token.strip()
            if not token:
                continue
            try:
                size, status = token.split(":")
                size = clean_size_for_barbour(size)
                stock = 1 if status.strip() == "有货" else 0
                detail.append(f"{size}:{stock}:0000000000000")
            except ValueError:
                continue
        if detail:
            info["Product Size Detail"] = ";".join(detail)

# ========== 主流程 ==========
def process_url(url, output_dir):
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    # 如需无头：options.add_argument("--headless=new")
    driver = uc.Chrome(options=options)

    try:
        print(f"\n🌐 正在抓取: {url}")
        driver.get(url)
        accept_cookies(driver)
        time.sleep(3)
        html = driver.page_source

        # 1) 解析（复用你已有的站点解析）
        info = parse_offer_info(html, url) or {}
        url_color = _normalize_color_from_url(url)

        # 2) 基础字段补齐（统一）
        info.setdefault("Brand", "Barbour")
        info.setdefault("Product Name", "No Data")
        info.setdefault("Product Color", url_color or "No Data")
        info.setdefault("Product Description", _extract_description(html))
        info.setdefault("Feature", _extract_features(html))
        info.setdefault("Site Name", "Outdoor and Country")
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
        ps, psd = _build_sizes_from_offers(offers, info["Product Gender"])
        info["Product Size"] = ps
        info["Product Size Detail"] = psd

        # 6) 类目（本地兜底，防止 category_utils 旧版误判）
        if not info.get("Style Category"):
            info["Style Category"] = _fallback_style_category(
                info.get("Product Name",""),
                info.get("Product Description",""),
                info.get("Product Code","") or ""
            )

        # ========= ✅ Outdoor 专属增强：写盘前一次性处理 =========
        _inject_price_from_offers(info)   # Outdoor 无价 → 从 offers 补
        _clean_sizes(info)                 # 尺码清洗（两行）
        _ensure_detail_from_size(info)     # 没 Detail 就从 Size 兜底

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
    finally:
        driver.quit()

def fetch_outdoor_product_offers_concurrent(max_workers=3):
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

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_url, url, output_dir) for url in urls]
        for _ in as_completed(futures):
            pass

if __name__ == "__main__":
    fetch_outdoor_product_offers_concurrent(max_workers=3)
