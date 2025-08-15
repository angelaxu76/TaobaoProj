
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

def parse_offer_info(html: str, url: str, site_name="Outdoor and Country") -> dict:
    import re
    from urllib.parse import urlparse, parse_qs, unquote_plus
    from bs4 import BeautifulSoup

    def _norm_color(s: str) -> str:
        """颜色标准化：URL 解码、统一斜杠空格、小写"""
        s = unquote_plus(s or "")
        s = re.sub(r'%2F', '/', s, flags=re.I)      # 万一还有残留 %2F
        s = re.sub(r'\s*/\s*', ' / ', s)            # 统一斜杠两边空格
        s = re.sub(r'\s+', ' ', s).strip().lower()  # 压缩空白并小写
        return s

    def _get_current_color_from_url(u: str) -> str:
        """从 URL 里读取 c 参数（人类可读，用于显示）；比对用 _norm_color。"""
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

    # 当前颜色（显示用）与其规范化版本（匹配用）
    current_color = _get_current_color_from_url(url)
    curr_norm = _norm_color(current_color)

    # 解析页面脚本里的映射
    colours = extract_js_map_array(js_text, "Colours")   # e.g. {'16898': 'Military Brown / Hollyhock', ...}
    sizes_map = extract_js_map_array(js_text, "Sizes")   # e.g. {'2292': 'UK: 8, ...'}
    stock_info = extract_stock_info_dict(js_text)        # e.g. {'2292-16898': {...}, ...}

    # 严格等值匹配：把 colours 的值也标准化为小写，然后等值比较拿 color_id
    norm_map = {k: _norm_color(v) for k, v in colours.items()} if colours else {}
    color_id = next((k for k, v in norm_map.items() if v == curr_norm), None)
    if not color_id:
        print(f"⚠️ 未找到颜色ID：current='{current_color}' (norm='{curr_norm}'); 可选={list(colours.values()) if colours else []}")

    # 颜色编码（主路：dataLayer）
    color_code = extract_color_code_from_datalayer(js_text)

    # 组装 offers（仅当有 stock & color_id 时过滤到该色；否则返回空列表）
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

            # 价格/库存字段做健壮转换
            raw_price = value.get("priceGbp", 0)
            try:
                price = float(raw_price)
            except Exception:
                try:
                    price = float(str(raw_price).replace(",", ""))
                except Exception:
                    price = 0.0

            try:
                availability = int(value.get("availability", 0))
            except Exception:
                availability = 0

            stock_status = "有货" if availability > 0 else "无货"
            can_order = availability > 0
            offers.append((uk_size, price, stock_status, can_order))

    return {
        "Product Name": product_name,
        "Product Color": current_color,
        "Product Color Code": color_code,
        "Site Name": site_name,
        "Product URL": url,
        "Offers": offers
    }
