# brands/ms/core/ms_fetch_product_info.py
# -*- coding: utf-8 -*-
"""
M&S 商品抓取 → 生成“鲸芽模式”格式化 TXT（Camper 对齐）
- 无需命令行参数，供 pipeline 直接调用：ms_fetch_product_info()
- 从大 JSON(__INITIAL_STATE__/__NEXT_DATA__/__NUXT__)提取每个 SKU 尺码与库存
- 生成 SizeMap / SizeDetail（dict），由 format_txt 渲染出：
    Product Size: <尺码:有货/无货;...>
    Product Size Detail: <尺码:库存:EAN;...>
- 兜底：若没有大 JSON，则从 DOM/文本提取整码，库存置 0
"""

import re
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import BRAND_CONFIG
from common_taobao.ingest.txt_writer import format_txt

# ============= 常量&品牌配置 =============
CFG = BRAND_CONFIG["marksandspencer"]
SAVE_PATH: Path = CFG["TXT_DIR"]
PRODUCT_URLS_FILE: Path = CFG["LINKS_FILE_LINGERIE"]
CHROMEDRIVER_PATH: str = CFG.get("CHROMEDRIVER_PATH", "")
MAX_WORKERS = 6

# 杯型排序（用于输出排序）
CUP_ORDER = ["AA", "A", "B", "C", "D", "DD", "E", "F", "G", "H", "J", "K"]

# ============= Driver 管理（与 camper 风格一致） =============
drivers_lock = threading.Lock()
_all_drivers: set = set()
thread_local = threading.local()

def create_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-features=Translate,MediaRouter,AutofillServerCommunication")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        caps = driver.capabilities
        print("Chrome:", caps.get("browserVersion"))
        print("ChromeDriver:", (caps.get("chrome") or {}).get("chromedriverVersion", ""))
    except Exception:
        pass
    return driver

def get_driver() -> webdriver.Chrome:
    if not hasattr(thread_local, "driver"):
        d = create_driver()
        thread_local.driver = d
        with drivers_lock:
            _all_drivers.add(d)
    return thread_local.driver

def shutdown_all_drivers():
    with drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except Exception:
                pass
        _all_drivers.clear()

# ============= 工具函数 =============
def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _to_num_str(price_text: str) -> str:
    if not price_text:
        return ""
    m = re.search(r"(\d+(?:\.\d{1,2})?)", price_text.replace(",", ""))
    return m.group(1) if m else ""

def _parse_json_ld(soup: BeautifulSoup) -> List[dict]:
    out = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            content = tag.string or tag.get_text() or ""
            if not content.strip():
                continue
            obj = json.loads(content)
            if isinstance(obj, dict):
                out.append(obj)
            elif isinstance(obj, list):
                out.extend([x for x in obj if isinstance(x, dict)])
        except Exception:
            continue
    return out

def _find_product_in_jsonld(jsonld_list: List[dict]) -> dict:
    product = {}
    for obj in reversed(jsonld_list):
        typ = obj.get("@type")
        if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
            product["name"] = obj.get("name") or product.get("name")
            product["code"] = obj.get("sku") or obj.get("mpn") or product.get("code")
            product["color"] = obj.get("color") or product.get("color")
            product["description"] = obj.get("description") or product.get("description")
            offers = obj.get("offers", {})
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                product["price"] = offers.get("price") or product.get("price")
                ps = offers.get("priceSpecification") or {}
                if isinstance(ps, dict) and ps.get("price"):
                    product["discount_price"] = ps.get("price")
    return product

# ============= 从大 JSON 中提取 SKU 库存 =============
def _norm_size_label(primary: str, secondary: str) -> str:
    p = (primary or "").strip().upper()
    s = (secondary or "").strip().upper()
    if not p or not s:
        return ""
    return f"{p}{s}"

def _walk_collect_skus(obj, out: List[Tuple[str, int]]):
    """
    在任意嵌套的 dict/list 中遍历，捕捉形如：
      size: { primarySize: "34", secondarySize: "D" } + inventory: { quantity: 12 }
    以及 size: { name: "34D" } 的变体。
    """
    if isinstance(obj, dict):
        size = obj.get("size")
        inv = obj.get("inventory") or obj.get("stock") or {}
        qty = inv.get("quantity")

        if isinstance(size, dict) and (("primarySize" in size and "secondarySize" in size) or "name" in size):
            primary = size.get("primarySize")
            secondary = size.get("secondarySize")
            if (not primary or not secondary) and isinstance(size.get("name"), str):
                m = re.match(r"^\s*(\d{2})([A-Z]{1,3})\s*$", size["name"].upper())
                if m:
                    primary, secondary = m.group(1), m.group(2)
            label = _norm_size_label(primary, secondary)
            if label:
                try:
                    q = int(qty) if qty is not None else 0
                except Exception:
                    q = 0
                out.append((label, q))

        for v in obj.values():
            _walk_collect_skus(v, out)

    elif isinstance(obj, list):
        for x in obj:
            _walk_collect_skus(x, out)

def _extract_sizes_with_quantity_from_state(state_obj) -> Dict[str, int]:
    """从 window.__INITIAL_STATE__/__NEXT_DATA__/__NUXT__ 等对象中收集 { '34D': 12, ... }"""
    pairs: List[Tuple[str, int]] = []
    try:
        _walk_collect_skus(state_obj, pairs)
    except Exception:
        pass
    agg: Dict[str, int] = {}
    for label, q in pairs:
        if not label:
            continue
        agg[label] = max(int(q), agg.get(label, 0))
    return agg

from urllib.parse import urlparse, parse_qs, unquote

def _color_from_url(url: str) -> str:
    """
    当页面/JSON 未提供颜色时，从 URL 兜底解析:
      https://.../p/xxxx?color=WHITE      -> WHITE
      https://.../p/xxxx?colour=WHITE_MIX -> WHITE_MIX
    解析后做一次规范化：下划线/连字符 -> 空格；大写转 Title Case（保留 'Mix' 等词）。
    """
    if not url:
        return ""
    try:
        q = parse_qs(urlparse(url).query)
        raw = q.get("color", q.get("colour", [""]))[0]
        if not raw:
            return ""
        s = unquote(raw).strip()
        # 统一清理：下划线/连字符 -> 空格
        s = s.replace("_", " ").replace("-", " ")
        # 标准化大小写（WHITE MIX -> White Mix；ivory -> Ivory）
        s = s.upper()
        # 保留特殊杯型词汇的 Title Case：DD/EE 不涉及颜色，这里只处理普通词
        s = " ".join(w.capitalize() for w in s.split())
        return s
    except Exception:
        return ""

# ============= 主解析（单 URL） =============
def process_product_url(url: str):
    try:
        driver = get_driver()
        print(f"\n🔍 访问: {url}")
        driver.get(url)
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(4)  # 给 JS 渲染时间

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # ---------- 基础字段：JSON-LD + 兜底 ----------
        title_tag = soup.find("title")
        name_from_title = _clean_text(re.sub(r"\s*[-–—].*", "", title_tag.text)) if title_tag else ""

        jsonld_list = _parse_json_ld(soup)
        p_jsonld = _find_product_in_jsonld(jsonld_list)

        # 名称
        product_name = _clean_text(p_jsonld.get("name") or name_from_title or "No Data")

        # 编码（M&S 常见 Txx/xxxx）
        product_code = p_jsonld.get("code") or ""
        if not product_code:
            body_txt = soup.get_text("\n")
            mcode = re.search(r"\bT\d{2}/[A-Z0-9]+", body_txt)
            if mcode:
                product_code = mcode.group(0)
        product_code = product_code or "No Data"

        # 颜色/描述
        product_color = _clean_text(p_jsonld.get("color") or "")  # 先用 JSON/LD
        if not product_color:  # 页面不给 → 用 URL 兜底
            product_color = _color_from_url(url)
        product_color = product_color or "No Data"



        description = _clean_text(p_jsonld.get("description") or "") or "No Data"





        # ---------- 价格/折扣价 ----------
        raw_price = _to_num_str(p_jsonld.get("price") or "")
        raw_discount = _to_num_str(p_jsonld.get("discount_price") or "")

        if raw_discount and raw_price and raw_discount != raw_price:
            # 情况1：原价 + 折扣价都有
            price = raw_price
            discount_price = raw_discount
        elif raw_price and not raw_discount:
            # 情况2：只有一个价格（正常价）
            price = raw_price
            discount_price = ""  # ✅ 空但存在
        elif not raw_price and raw_discount:
            # 情况3：只有折扣价
            price = raw_discount
            discount_price = ""
        else:
            price = "No Data"
            discount_price = ""









        # ---------- 尺码与库存：优先读取大 JSON ----------
        size_qty_map: Dict[str, int] = {}

        # 1) window 全局对象
        state_obj = None
        try:
            state_obj = driver.execute_script(
                "return (window.__INITIAL_STATE__ || window.__NEXT_DATA__ || window.__NUXT__ || window.initialState || null)"
            )
        except Exception:
            state_obj = None

        if state_obj:
            size_qty_map = _extract_sizes_with_quantity_from_state(state_obj)

        # 2) 若还为空，遍历 <script> 里的 JSON 文本再兜底一次
        if not size_qty_map:
            for tag in soup.find_all("script"):
                txt = (tag.string or tag.get_text() or "").strip()
                if not txt or len(txt) < 50:
                    continue
                if not (txt.startswith("{") or txt.startswith("[")) and "primarySize" not in txt and "secondarySize" not in txt:
                    continue
                cleaned = txt.replace("undefined", "null")
                try:
                    obj = json.loads(cleaned)
                except Exception:
                    continue
                sub = _extract_sizes_with_quantity_from_state(obj)
                if sub:
                    for k, v in sub.items():
                        size_qty_map[k] = max(v, size_qty_map.get(k, 0))
                    break

        # 3) 仍为空 → DOM/纯文本兜底（整码，库存=0）
        if not size_qty_map:
            rough_sizes = set()
            # select/按钮里的整码
            for opt in soup.select('select[name*=size] option'):
                t = _clean_text(opt.get_text()).upper()
                if t and "SELECT" not in t and re.search(r"\b\d{2}[A-Z]{1,3}\b", t):
                    rough_sizes.add(t)
            for el in soup.select('[data-testid*=size], button, a'):
                lbl = (el.get("aria-label") or el.get("data-size") or el.get("data-value") or "").strip().upper()
                if lbl and re.search(r"\b\d{2}[A-Z]{1,3}\b", lbl):
                    rough_sizes.add(lbl)
            if not rough_sizes:
                text_all = soup.get_text(" ").upper()
                for m in re.finditer(r"\b\d{2}[A-Z]{1,3}\b", text_all):
                    rough_sizes.add(m.group(0))
            size_qty_map = {s: 0 for s in rough_sizes}

        # ---------- 生成 SizeMap / SizeDetail（dict） ----------
        if size_qty_map:
            def _sort_key(sz: str):
                m = re.match(r"^(\d{2})([A-Z]{1,3})$", sz)
                band = int(m.group(1)) if m else 0
                cup = (m.group(2) if m else "").upper()
                cup_idx = CUP_ORDER.index(cup) if cup in CUP_ORDER else 999
                return (band, cup_idx, cup)

            ordered = sorted(size_qty_map.items(), key=lambda kv: _sort_key(kv[0]))
            size_map = {sz: ("有货" if qty > 0 else "无货") for sz, qty in ordered}
            # EAN 暂无：可用 "" 或 "0000000000000"
            size_detail = {sz: {"stock_count": int(qty), "ean": "0000000000000"} for sz, qty in ordered}
        else:
            size_map = {}
            size_detail = {}

        # ---------- 其它字段 ----------
        gender = "女款"  # 胸罩默认女款
        style_category = "内衣/文胸"

        # ---------- 写出 TXT ----------
        info = {
            "Product Code": product_code,
            "Product Name": product_name,
            "Product Description": description,
            "Product Gender": gender,
            "Product Color": product_color,
            "Product Price": price,
            "Adjusted Price": discount_price if discount_price else 0,
            "Product Material": "No Data",
            "Style Category": style_category,
            "Feature": "No Data",

            # ✅ 交由 format_txt 渲染成两行
            "SizeMap": size_map,
            "SizeDetail": size_detail,

            "Source URL": url
        }

        SAVE_PATH.mkdir(parents=True, exist_ok=True)
        filepath = SAVE_PATH / f"{product_code.replace('/', '_')}.txt"

        try:
            format_txt(info, filepath, brand="marksandspencer")
        except TypeError:
            format_txt(info, filepath)

        print(f"✅ 完成 TXT: {filepath.name}")

    except Exception as e:
        print(f"❌ 错误: {url} - {e}")

# ============= 无参入口（供 pipeline 调用） =============
def fetch_product_info(max_workers: int = MAX_WORKERS):
    SAVE_PATH.mkdir(parents=True, exist_ok=True)
    urls_path = Path(PRODUCT_URLS_FILE)
    if not urls_path.exists():
        print(f"⚠️ 未找到 URL 列表文件：{urls_path}")
        return

    with urls_path.open("r", encoding="utf-8", errors="ignore") as f:
        urls = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_product_url, u) for u in urls]
            for fut in as_completed(futures):
                fut.result()
    finally:
        shutdown_all_drivers()

# 可独立运行调试（生产中建议由 pipeline 调用）
if __name__ == "__main__":
    fetch_product_info()
