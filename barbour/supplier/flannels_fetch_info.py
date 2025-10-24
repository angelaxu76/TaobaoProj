import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

###############################################################################
# 配置区
###############################################################################

HEADERS = {
    # 模拟正常浏览器，避免被403/简易bot拦
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

OOS_KEYWORDS = ["out of stock", "sold out", "unavailable", "no stock", "oos"]

# 性别猜测关键字
GENDER_PATTERNS = {
    "男款": ["men", "mens", "men's", "male"],
    "女款": ["women", "womens", "women's", "ladies", "female", "ladys", "ladies'"],
    "童款": ["kids", "junior", "youth", "boy", "girl", "boys", "girls", "child"],
}

# 简单类目猜测
CATEGORY_RULES = [
    ("外套/夹克", ["jacket", "wax", "quilt", "quilted", "parka", "coat", "gilet", "fleece"]),
    ("上衣", ["t-shirt", "tee", "shirt", "polo", "sweat", "hoodie", "sweatshirt"]),
    ("裤装/下装", ["trouser", "pant", "jean", "short", "shorts", "cargo", "track pant"]),
]


###############################################################################
# 基础工具
###############################################################################

def _clean_text(t: str) -> str:
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()


def _guess_gender(page_text: str) -> str:
    low = page_text.lower()
    scores = {g: 0 for g in GENDER_PATTERNS.keys()}
    for g_cn, words in GENDER_PATTERNS.items():
        for w in words:
            if w in low:
                scores[g_cn] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "No Data"


def _guess_category(name: str, desc: str) -> str:
    blob = f"{name} {desc}".lower()
    for label, kws in CATEGORY_RULES:
        for w in kws:
            if w in blob:
                return label
    return "No Data"


def _extract_code_from_url(url: str) -> str:
    """
    https://www.flannels.com/mens-powell-quilted-jacket-605441
    -> 605441
    """
    path_tail = urlparse(url).path.strip("/").split("/")[-1]
    m = re.search(r"([A-Za-z0-9_-]+)$", path_tail)
    return m.group(1) if m else "No Data"


###############################################################################
# 抓页面
###############################################################################

def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


###############################################################################
# 价格解析
###############################################################################

def _extract_price_info(soup: BeautifulSoup) -> (str, str):
    """
    返回 (Product Price, Adjusted Price)
    逻辑：
      1. 先拿当前售价（现价） → meta[name="twitter:data1"] 里的 £xxx
      2. 再尝试正文中找原价/划线价
      3. 如果存在 原价>现价 → Product Price=原价, Adjusted Price=现价
      4. 否则 → Product Price=现价, Adjusted Price="No Data"
    """
    # Step 1: 当前价 (现价)
    now_price_val = None
    node_now_meta = soup.find("meta", attrs={"name": "twitter:data1"})
    if node_now_meta and node_now_meta.get("content"):
        # e.g. "£145"
        m = re.search(r"£\s*([0-9]+(?:\.[0-9]+)?)", node_now_meta["content"])
        if m:
            now_price_val = float(m.group(1))

    # 兜底：有些站点也放在 meta[property="product:price:amount"]
    if now_price_val is None:
        node_alt = soup.find("meta", attrs={"property": "product:price:amount"})
        if node_alt and node_alt.get("content"):
            try:
                now_price_val = float(node_alt["content"])
            except:
                pass

    # Step 2: 原价 (划线价) in body
    # 常见结构是 "Was £179" / "RRP £179" / "£179.00" in something like class*="PreviousPrice" or "rrp"
    original_price_val = None

    body_text_candidates = []
    for tag in soup.find_all(True):
        cls = " ".join(tag.get("class", [])).lower()
        if any(k in cls for k in ["previous", "wasprice", "rrp", "was-price", "rrp-price", "prevprice", "was"]):
            txt = _clean_text(tag.get_text())
            if "£" in txt:
                body_text_candidates.append(txt)

    # 也可以顺便找有 "Was £" / "RRP £"
    plain_text = soup.get_text(" ", strip=True)
    for m in re.findall(r"(?:Was|RRP|Was Price|Previous Price)\s*£\s*([0-9]+(?:\.[0-9]+)?)", plain_text, re.I):
        body_text_candidates.append("£" + m)

    # 从候选里挑最大的一个当原价（因为原价通常>=现价）
    vals = []
    for t in body_text_candidates:
        mm = re.findall(r"£\s*([0-9]+(?:\.[0-9]+)?)", t)
        for v in mm:
            try:
                vals.append(float(v))
            except:
                pass
    if vals:
        original_price_val = max(vals)

    # Step 3: 合成返回
    def _fmt(v):
        return f"{v:.2f}"

    if now_price_val is None and original_price_val is None:
        # 啥都没有
        return "No Data", "No Data"

    if now_price_val is not None and original_price_val is not None and now_price_val < original_price_val:
        # 真正打折
        return _fmt(original_price_val), _fmt(now_price_val)

    # 没检测到明确打折，只有一个价
    if now_price_val is not None:
        return _fmt(now_price_val), "No Data"

    # 极小概率：只有原价（但没拿到现价）
    return _fmt(original_price_val), "No Data"


###############################################################################
# 颜色解析
###############################################################################

def _extract_color(soup: BeautifulSoup) -> str:
    """
    常见是 "Colour: Black" / "Color: Navy" 之类在规格表里，
    或按钮上有 data-colour="Black" 的元素。
    """
    # 1) data-attribute
    color_el = soup.find(attrs={"data-colour": True})
    if color_el:
        c = _clean_text(color_el.get("data-colour"))
        if c:
            return c

    # 2) 文本里类似 "Colour Black"
    spec_text = soup.get_text(" ", strip=True)
    m = re.search(r"(?:Colour|Color)\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 /\-]+)", spec_text, flags=re.I)
    if m:
        return _clean_text(m.group(1))

    return "No Data"


###############################################################################
# 描述 / 材质
###############################################################################

def _extract_description(soup: BeautifulSoup) -> str:
    """
    我们尝试抓产品描述块，比如 "Product description", "Details", "Product Details"
    通常在 <section> / <div> 带有 'description', 'details' 关键字的 class
    """
    candidates = []
    for tag in soup.find_all(["div", "section", "p", "li"]):
        cls = " ".join(tag.get("class", [])).lower()
        if any(k in cls for k in ["description", "details", "product-description", "productdetails"]):
            txt = _clean_text(tag.get_text(" ", strip=True))
            if len(txt) > 30:  # 排除太短的无意义块
                candidates.append(txt)
    if candidates:
        # 取最长的作为主描述
        return max(candidates, key=len)

    # fallback: 没找到明确块，就整页里找 "Product Description" 后面的几句
    full_text = soup.get_text("\n", strip=True)
    m = re.search(r"Product Description[:\n]+(.{50,400})", full_text, flags=re.I | re.S)
    if m:
        return _clean_text(m.group(1))

    return "No Data"


def _extract_material(soup: BeautifulSoup) -> str:
    """
    找材质/成分，常见关键字：Material, Fabric, Composition, Outer, Shell
    一般在要么规格表 <li> 里，要么详情块里列出了 "Outer: 100% Cotton" 之类。
    """
    MATERIAL_KEYS = ["material", "fabric", "composition", "outer", "shell", "upper", "lining", "wax", "cotton", "polyester", "leather"]

    best = ""
    for tag in soup.find_all(["li", "p", "div", "span"]):
        txt = _clean_text(tag.get_text(" ", strip=True))
        low = txt.lower()
        if any(k in low for k in MATERIAL_KEYS):
            # 过滤掉太短（比如只有 "Material:"）
            if len(txt) >= 10 and len(txt) > len(best):
                best = txt
    return best if best else "No Data"


###############################################################################
# 尺码 + 库存
###############################################################################

def _extract_sizes(soup: BeautifulSoup) -> (str, str):
    """
    返回:
      Product Size
      Product Size Detail

    我们找类似尺码选择区域的元素：
    - <button ...>M</button>
    - <li class="SizeOption ...">XL</li>
    并用 disabled / aria-disabled / 'sold out' / 'oos' 等判断库存。

    输出格式例子：
      Product Size:
        "S:有货;M:有货;L:无货;XL:有货"
      Product Size Detail:
        "S:3:0000000000000;M:3:0000000000000;L:0:0000000000000;XL:3:0000000000000"
    """
    sizes_found = {}  # size_label -> {"status": "有货"/"无货", "ean": "0000000000000"}

    def mark(size_label: str, is_oos: bool):
        size_label = _clean_text(size_label)
        if not size_label:
            return
        status = "无货" if is_oos else "有货"
        prev = sizes_found.get(size_label)
        if prev:
            # 如果之前说无货，现在说有货，就升级为有货
            if prev["status"] == "无货" and status == "有货":
                prev["status"] = "有货"
        else:
            sizes_found[size_label] = {
                "status": status,
                "ean": "0000000000000",
            }

    # 我们猜“尺码按钮”通常会带 size/sizeOption/variant 的 class
    for el in soup.find_all(["button", "li", "label", "div", "span"]):
        cls = " ".join(el.get("class", [])).lower()
        if not re.search(r"(size|variant|option)", cls):
            continue

        raw_txt = _clean_text(el.get_text(" ", strip=True))
        # candidate size text类似 "S", "M", "L", "XL", "XXL", "3XL", "32", "34"
        if not raw_txt:
            continue

        low_all = " ".join([raw_txt.lower(), cls])
        disabled_flag = (
            el.has_attr("disabled")
            or el.get("aria-disabled") == "true"
            or "disabled" in cls
            or "unavailable" in cls
            or "soldout" in cls
            or "oos" in cls
        )

        # 关键字再兜底
        if not disabled_flag:
            for kw in OOS_KEYWORDS:
                if kw in low_all:
                    disabled_flag = True
                    break

        mark(raw_txt, disabled_flag)

    # 排序：字母尺码按 XS,S,M,L,XL,XXL,3XL...；数字尺码按数值
    def is_number_size(s: str) -> bool:
        return bool(re.fullmatch(r"\d+", s))

    alpha_sizes = [s for s in sizes_found if not is_number_size(s)]
    num_sizes = [s for s in sizes_found if is_number_size(s)]

    # 选择主体系：谁多用谁
    use_alpha = len(alpha_sizes) >= len(num_sizes)

    if use_alpha:
        ORDER = ["2XS","XS","S","M","L","XL","XXL","XXXL","3XL","4XL"]
        order_map = {v:i for i,v in enumerate(ORDER)}
        final_sizes = sorted(alpha_sizes, key=lambda x: order_map.get(x, 9999))
    else:
        def _to_int(v):
            try:
                return int(v)
            except:
                return 9999
        final_sizes = sorted(num_sizes, key=_to_int)

    # 组装输出
    ps_list = []
    psd_list = []
    for size_key in final_sizes:
        st = sizes_found[size_key]["status"]  # 有货/无货
        qty = 3 if st == "有货" else 0
        ean = sizes_found[size_key]["ean"]
        ps_list.append(f"{size_key}:{st}")
        psd_list.append(f"{size_key}:{qty}:{ean}")

    product_size = ";".join(ps_list) if ps_list else "No Data"
    product_size_detail = ";".join(psd_list) if psd_list else "No Data"

    return product_size, product_size_detail


###############################################################################
# 主解析函数
###############################################################################

def parse_flannels_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # Product Name (一般在 <h1> / <meta property="og:title">)
    name = "No Data"
    h1 = soup.find("h1")
    if h1 and _clean_text(h1.get_text()):
        name = _clean_text(h1.get_text())
    else:
        ogt = soup.find("meta", attrs={"property": "og:title"})
        if ogt and ogt.get("content"):
            name = _clean_text(ogt["content"])

    # Description
    desc = _extract_description(soup)

    # Material
    material = _extract_material(soup)

    # Gender guess
    gender = _guess_gender(" ".join([name, desc, url]))

    # Category
    style_category = _guess_category(name, desc)

    # Color
    color = _extract_color(soup)

    # Code
    code = _extract_code_from_url(url)

    # Price / Adjusted Price
    product_price, adjusted_price = _extract_price_info(soup)

    # Sizes
    product_size, product_size_detail = _extract_sizes(soup)

    info = {
        "Product URL": url,
        "Product Name": name,
        "Product Code": code,
        "Product Gender": gender,
        "Product Color": color,
        "Product Price": product_price,
        "Adjusted Price": adjusted_price,
        "Product Material": material,
        "Product Description": desc,
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Style Category": style_category,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return info


###############################################################################
# 写 TXT
###############################################################################

def write_product_txt(info: dict, out_dir: Path):
    """
    out_dir: 例如 D:/TB/Products/barbour/publication/flannels/TXT
    文件名: {Product Code}.txt
    如果没有 Code，就用最后一段 URL 兜底
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    code = info.get("Product Code", "No Data")
    if not code or code == "No Data":
        code = _extract_code_from_url(info["Product URL"]) or "NoData"

    outfile = out_dir / f"{code}.txt"

    order_keys = [
        "Product URL",
        "Product Name",
        "Product Code",
        "Product Gender",
        "Product Color",
        "Product Price",
        "Adjusted Price",
        "Product Material",
        "Product Description",
        "Product Size",
        "Product Size Detail",
        "Style Category",
        "Timestamp",
    ]

    lines = []
    for k in order_keys:
        v = info.get(k, "No Data")
        lines.append(f"{k}: {v}")

    outfile.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 写入: {outfile}")


###############################################################################
# 批量 & 主入口
###############################################################################

def fetch_and_save_single(url: str, out_dir: Path):
    html = fetch_html(url)
    info = parse_flannels_page(html, url)
    write_product_txt(info, out_dir)


def fetch_and_save_from_list(url_list_file: Path, out_dir: Path):
    urls = [
        line.strip()
        for line in url_list_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for url in urls:
        fetch_and_save_single(url, out_dir)


# 兼容你之前 pipeline 习惯的入口函数
def flannels_fetch_info(max_workers: int = 1):
    """
    模拟 houseoffraser_fetch_info(max_workers=1) 的风格：
    - 读取链接列表文件
    - 逐个抓（这里先不做多线程，max_workers 只是占位保持接口兼容）
    你可以后面像之前那样加 ThreadPoolExecutor 来并发，如果需要。
    """
    URL_LIST_FILE = Path(r"D:/TB/Products/barbour/publication/flannels/product_links.txt")
    OUTPUT_DIR = Path(r"D:/TB/Products/barbour/publication/flannels/TXT")

    urls = [
        line.strip()
        for line in URL_LIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for url in urls:
        fetch_and_save_single(url, OUTPUT_DIR)


if __name__ == "__main__":
    # 单条测试
    test_url = "https://www.flannels.com/mens-powell-quilted-jacket-605441"
    out_dir = Path(r"D:/TB/Products/barbour/publication/flannels/TXT")
    fetch_and_save_single(test_url, out_dir)

    # 批量测试（如果你已经有 product_links.txt）
    # URL_LIST_FILE = Path(r"D:/TB/Products/barbour/publication/flannels/product_links.txt")
    # fetch_and_save_from_list(URL_LIST_FILE, out_dir)
