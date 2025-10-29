# === outdoorandcountry_parse_offer_info.py ===
import re
import json
from bs4 import BeautifulSoup
import demjson3
from urllib.parse import urlparse, parse_qs, unquote_plus

def extract_js_map_array(js_text: str, var_name: str) -> dict:
    pattern = re.compile(rf"{var_name}\[['\"](?P<key>[^'\"]+)['\"]\]\s*=\s*['\"](?P<val>[^'\"]+)['\"];")
    return {m.group("key"): m.group("val") for m in pattern.finditer(js_text)}

def extract_stock_info_dict(js_text: str) -> dict:
    pattern = re.compile(r"var stockInfo\s*=\s*({.*?});\s*", re.DOTALL)
    match = pattern.search(js_text)
    if not match:
        print("❌ 无法找到 stockInfo 段落")
        return {}
    raw = match.group(1)
    try:
        return demjson3.decode(raw)
    except Exception as e:
        print(f"❌ demjson3 解码失败: {e}")
        return {}

def extract_color_code_from_datalayer(js_text: str) -> str:
    try:
        match = re.search(r'"products"\s*:\s*(\[[\s\S]*?\])', js_text)
        if not match:
            print("❌ 未找到 products 段")
            return "Unknown"
        products_str = match.group(1)
        products = demjson3.decode(products_str)
        if not products or not isinstance(products, list):
            print("❌ products 解码失败")
            return "Unknown"
        first_sku = products[0].get("sku", "").strip()
        if len(first_sku) >= 11:
            candidate = first_sku[:11]
            if re.fullmatch(r"[A-Z]{3}\d{4}[A-Z]{2}\d{2}", candidate):
                return candidate
        print(f"⚠️ SKU 无法匹配 color_code 模式: {first_sku}")
        return "Unknown"
    except Exception as e:
        print(f"❌ 解析 dataLayer 产品失败: {e}")
        return "Unknown"

# ===== 新增：稳健的价格提取函数 =====
PRICE_RE = re.compile(r"£\s*([\d]+(?:\.\d+)?)")

def extract_prices(html: str):
    """
    返回 (original_price, current_price)，字符串形式，如 ('349.00', '244.30')
    优先级：
      1) dataLayer 的 priceRrp / price
      2) 内嵌 JS 的 priceHeading
      3) 主容器 #item-price 的 .saleold / .sale
      4) 兜底：OG 的 og:price:amount（仅现价）
    """
    orig = curr = None

    # ① dataLayer（最稳）
    m = re.search(
        r'dataLayer\.push\(\s*{[^}]*"priceRrp"\s*:\s*"(?P<rrp>[\d.]+)".*?"price"\s*:\s*"?(?P<price>[\d.]+)"?',
        html, re.S)
    if m:
        orig = m.group("rrp")
        curr = m.group("price")

    # ② 内嵌 JS 的 priceHeading
    if not (orig and curr):
        mh = re.search(r'priceHeading\"\s*:\s*\"(?P<h>[^\"\\]+)\"', html)
        if mh:
            h = mh.group("h")
            olds = re.search(r"<span class='saleold'>\s*£\s*([\d.]+)\s*</span>", h)
            nows = re.search(r"<span class='sale'>\s*NOW\s*£\s*([\d.]+)\s*</span>", h)
            if olds: orig = orig or olds.group(1)
            if nows: curr = curr or nows.group(1)

    # ③ 主容器 #item-price
    if not (orig and curr):
        mo = re.search(r'id="item-price"[^>]*>.*?<span class="saleold">([^<]+)</span>', html, re.S)
        if mo:
            m2 = PRICE_RE.search(mo.group(1))
            if m2: orig = orig or m2.group(1)
        mc = re.search(r'id="item-price"[^>]*>.*?<span class="sale">NOW\s*([^<]+)</span>', html, re.S)
        if mc:
            m2 = PRICE_RE.search(mc.group(1))
            if m2: curr = curr or m2.group(1)

    # ④ 兜底：仅现价
    if not curr:
        mo = re.search(r'og:price:amount" content="([\d.]+)"', html)
        if mo: curr = mo.group(1)

    return (orig, curr)

def parse_offer_info(html: str, url: str, site_name="Outdoor and Country") -> dict:
    def _norm_color(s: str) -> str:
        s = unquote_plus(s or "")
        s = re.sub(r'%2F', '/', s, flags=re.I)
        s = re.sub(r'\s*/\s*', ' / ', s)
        s = re.sub(r'\s+', ' ', s).strip().lower()
        return s

    def _get_current_color_from_url(u: str) -> str:
        qs = parse_qs(urlparse(u).query)
        c = qs.get('c', [''])[0]
        c = unquote_plus(c)
        c = re.sub(r'%2F', '/', c, flags=re.I)
        c = re.sub(r'\s*/\s*', ' / ', c)
        return re.sub(r'\s+', ' ', c).strip() or "Unknown"

    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")
    js_text = "\n".join(script.get_text() for script in scripts if script.get_text())

    # 产品名
    product_name = soup.title.string.strip() if soup.title else "Unknown Product"

    # 当前颜色
    current_color = _get_current_color_from_url(url)
    curr_norm = _norm_color(current_color)

    # 解析页面脚本里的映射
    colours = extract_js_map_array(js_text, "Colours")
    sizes_map = extract_js_map_array(js_text, "Sizes")
    stock_info = extract_stock_info_dict(js_text)

    # 匹配 color_id
    norm_map = {k: _norm_color(v) for k, v in (colours or {}).items()}
    color_id = next((k for k, v in norm_map.items() if v == curr_norm), None)
    if not color_id:
        print(f"⚠️ 未找到颜色ID：current='{current_color}' (norm='{curr_norm}'); 可选={list((colours or {}).values())}")

    # 颜色编码（主路：dataLayer）
    color_code = extract_color_code_from_datalayer(js_text)

    # ===== 新增：解析整页原价/折扣价 =====
    original_price_gbp, discount_price_gbp = extract_prices(html)
    # 无折扣时，降级为同价
    if (not discount_price_gbp) and original_price_gbp:
        discount_price_gbp = original_price_gbp

    # 组装 offers（仅当有 stock & color_id 时过滤到该色）
    offers = []
    if stock_info and color_id:
        for key, value in stock_info.items():
            if "-" not in key:
                continue
            size_id, c_id = key.split("-", 1)
            if c_id != color_id:
                continue

            size_str = sizes_map.get(size_id, size_id)
            uk_size = size_str.split(",")[0].replace("UK:", "").strip()

           # 价格保持原样
            raw_price = value.get("priceGbp", 0)
            try:
                price = float(raw_price)
            except Exception:
                try:
                    price = float(str(raw_price).replace(",", ""))
                except Exception:
                    price = 0.0

            # ✅ 以 stockLevelMessage 判定有/无货
            msg = str(value.get("stockLevelMessage", "")).lower()
            no_stock = any(k in msg for k in [
                "unavailable online",        # sorry this item is currently unavailable online
                "out of stock",
            ])
            has_stock_kw = any(k in msg for k in [
                "available online",
                "in stock",
                "more than",                 # e.g. "More than 10 available online"
                "available",
            ])
            has_stock = (not no_stock) and has_stock_kw

            # 若两者都没命中，才回退 availability
            if not no_stock and not has_stock:
                try:
                    availability = int(value.get("availability", 0))
                except Exception:
                    availability = 0
                has_stock = availability in (1, 2)

            stock_status = "有货" if has_stock else "无货"
            can_order    = has_stock   # 仅向下游传递用；DB 已不使用该列

            offers.append((uk_size, price, stock_status, can_order))


    return {
        "Product Name": product_name,
        "Product Color": current_color,
        "Product Color Code": color_code,
        "Site Name": site_name,
        "Product URL": url,
        # ===== 新增两个字段：整页原价/现价 =====
        "original_price_gbp": original_price_gbp or "0",
        "discount_price_gbp": discount_price_gbp or "0",
        "Offers": offers
    }
