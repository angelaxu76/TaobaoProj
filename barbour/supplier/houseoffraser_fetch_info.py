# -*- coding: utf-8 -*-
"""
House of Fraser | Barbour 商品抓取（统一 TXT 模板版）
- 与其它站点保持一致：零参数、从 config 读取路径与链接
- 爬取技术：Selenium + BeautifulSoup（与现有 allweathers/outdoorandcountry 一致）
- 写入：common_taobao.txt_writer.format_txt（与现有站点一致）

输出字段补齐：
- Product Description：meta[property="og:description"]
- Feature：#DisplayAttributes li → "key: value; ..."
- Product Material：Feature 中 Fabric/Material/Shell 的值（无则 No Data）
- Product Size：从 #sizeDdl > option 解析（greyOut=无货）→ "6:无货;8:有货;..."
- Product Size Detail：与上对应，"size:1/0:0000000000000"（有货=1，无货=0）
- Product Price：优先 DOM 提取的现价；若未取到保留 "No Data"
- Adjusted Price：留空，由下游 price_utils 计算
- Style Category：基于标题关键字的简单推断（jacket / quilted jacket / wax jacket）
- Product Code：HOF 页面无，固定 "No Data"
"""

import re
import time
from pathlib import Path
from typing import Optional, List, Tuple

import undetected_chromedriver as uc
from bs4 import BeautifulSoup

from config import BARBOUR
from common_taobao.txt_writer import format_txt  # 统一写入模板（与你现有站点一致）
from barbour.core.site_utils import assert_site_or_raise as canon

# ========== 站点级常量 ==========
SITE_NAME = canon("houseoffraser")
EAN_PLACEHOLDER = "0000000000000"

LINKS_FILE = BARBOUR["LINKS_FILES"]["houseoffraser"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["houseoffraser"]
TXT_DIR.mkdir(parents=True, exist_ok=True)  # 确保目录存在


# ========== Selenium 驱动（与现有风格一致） ==========
def get_driver():
    options = uc.ChromeOptions()
    # 如需无头：options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options)
    return driver


# ========== 工具函数 ==========
def _extract_gender(title: str, soup: BeautifulSoup) -> str:
    """
    从标题/meta/breadcrumb 推断性别
    """
    t = (title or "").lower()
    if "women" in t:
        return "女款"
    if "men" in t:
        return "男款"
    if "kids" in t or "girls" in t or "boys" in t:
        return "童款"
    # 兜底：从 meta og:title 判断
    m = soup.find("meta", attrs={"property": "og:title"})
    if m and "women" in m.get("content", "").lower():
        return "女款"
    return "No Data"


def _extract_color(soup: BeautifulSoup) -> str:
    """
    从颜色选择器中提取当前颜色
    """
    ul = soup.find("ul", id="ulColourImages")
    if ul:
        li = ul.find("li", attrs={"aria-checked": "true"})
        if li:
            # data-text 属性优先
            txt = li.get("data-text") or ""
            if txt.strip():
                return _clean_text(txt)
            # 再尝试 <img alt>
            img = li.find("img")
            if img and img.get("alt"):
                return _clean_text(img["alt"])
    return "No Data"


def _clean_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _price_from_text_block(text: str) -> Tuple[Optional[float], Optional[float]]:
    """
    从一段并排价格字符串里提取 (current, original)
    例如 "£95.00 £189.00" → (95.00, 189.00)
    经验策略：第一个视为现价；最大值视为原价（若比现价大）
    """
    vals = re.findall(r"£?\s*([0-9]+(?:\.[0-9]{1,2})?)", text or "")
    nums = [float(v) for v in vals]
    if not nums:
        return (None, None)
    curr = nums[0]
    orig = None
    if len(nums) >= 2:
        mx = max(nums)
        if mx > curr:
            orig = mx
        else:
            orig = nums[-1]
    return (curr, orig)

def _extract_title(soup: BeautifulSoup) -> str:
    # 取 <title>，去掉站点后缀
    t = _clean_text(soup.title.get_text()) if soup.title else "No Data"
    t = re.sub(r"\s*\|\s*House of Fraser\s*$", "", t, flags=re.I)
    return t or "No Data"

def _extract_og_description(soup: BeautifulSoup) -> str:
    m = soup.find("meta", attrs={"property": "og:description"})
    return _clean_text(m["content"]) if (m and m.get("content")) else "No Data"

def _extract_features_and_material(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    从 #DisplayAttributes li 拿特征列表，并从中抽取 Fabric/Material/Shell 等作为 Product Material
    """
    ul = soup.find("ul", id="DisplayAttributes")
    features = []
    material = ""
    if ul:
        for li in ul.find_all("li"):
            k = li.find("span", class_="feature-name")
            v = li.find("span", class_="feature-value")
            key = _clean_text(k.get_text() if k else "")
            val = _clean_text(v.get_text() if v else "")
            if key and val:
                features.append(f"{key}: {val}")
                if not material and key.lower() in {"fabric", "material", "shell", "outer"}:
                    material = val
    feat_str = "; ".join(features) if features else "No Data"
    return feat_str, (material or "No Data")

def _extract_prices(soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
    """
    从多个常见节点里凑一段价格文本，然后调用 _price_from_text_block
    """
    blocks = []
    # 常见类名/ID（HOF 主题可能变化，尽量多路收集）
    for sel in [
        {"id": "lblSellingPrice"},
        {"class_": re.compile(r"(product-price|price-now|now-price|current|selling)", re.I)},
        {"class_": re.compile(r"(prices?|productPrices?)", re.I)},
    ]:
        node = soup.find(attrs=sel)
        if node:
            blocks.append(node.get_text(" ", strip=True))
    # WAS/Was 节点
    was_nodes = soup.find_all(string=re.compile(r"\bwas\b", re.I))
    for n in was_nodes:
        blocks.append(str(n))
        if getattr(n, "parent", None):
            blocks.append(n.parent.get_text(" ", strip=True))
    merged = " | ".join({b for b in blocks if b})
    return _price_from_text_block(merged)

def _extract_size_offers(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    """
    解析 #sizeDdl > option
    返回 [(norm_size, stock_status)]；greyOut 或 title 含 'out of stock' → 无货，否则 有货
    """
    sel = soup.find("select", id="sizeDdl")
    results: List[Tuple[str, str]] = []
    if not sel:
        return results
    for opt in sel.find_all("option"):
        txt = _clean_text(opt.get_text())
        if not txt or txt.lower().startswith("select"):
            continue
        cls = opt.get("class") or []
        title = _clean_text(opt.get("title") or "")
        oos = ("greyOut" in cls) or ("out of stock" in title.lower())
        status = "无货" if oos else "有货"
        # 归一：把 "8 (XS)" → "8"
        norm = re.sub(r"\s*\(.*?\)\s*", "", txt).strip()
        norm = re.sub(r"^(UK|EU|US)\s+", "", norm, flags=re.I)
        results.append((norm, status))
    return results

def _build_size_lines(pairs: List[Tuple[str, str]]) -> Tuple[str, str]:
    """
    - Product Size: "8:有货;10:有货;..."
    - Product Size Detail: "8:1:000...;10:1:000...;..."（有货=1，无货=0）
    对同尺码多次出现：有货优先覆盖
    """
    bucket = {}
    for size, status in pairs or []:
        prev = bucket.get(size)
        if prev is None or (prev == "无货" and status == "有货"):
            bucket[size] = status
    # 排序：女款优先用 6,8,10,12... 的自然次序；否则按数字优先、再字母
    def _key(k: str):
        m = re.fullmatch(r"\d{1,3}", k)
        return (0, int(k)) if m else (1, k)
    ordered = sorted(bucket.keys(), key=_key)
    ps = ";".join(f"{k}:{bucket[k]}" for k in ordered)
    psd = ";".join(f"{k}:{3 if bucket[k]=='有货' else 0}:{EAN_PLACEHOLDER}" for k in ordered)
    return ps or "No Data", psd or "No Data"

def _infer_style_category(name: str) -> str:
    n = (name or "").lower()
    if "jacket" in n and "quilt" in n:
        return "quilted jacket"
    if "jacket" in n and "wax" in n:
        return "wax jacket"
    if "jacket" in n:
        return "jacket"
    return "casual wear"


# ========== 解析与写盘 ==========
def parse_and_build_info(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    description = _extract_og_description(soup)
    features, material = _extract_features_and_material(soup)
    curr_price, orig_price = _extract_prices(soup)
    pairs = _extract_size_offers(soup)
    product_size, product_size_detail = _build_size_lines(pairs)

    info = {
        "Product Code": "No Data",               # HOF 无编码
        "Product Name": title,
        "Product Description": description or "No Data",
        "Product Gender": _extract_gender(title, soup),
        "Product Color": _extract_color(soup),
        "Product Price": f"{curr_price:.2f}" if curr_price is not None else "No Data",
        "Adjusted Price": "",                    # 由下游计算
        "Product Material": material or "No Data",
        "Style Category": _infer_style_category(title),
        "Feature": features or "No Data",
        "Product Size": product_size,
        "Product Size Detail": product_size_detail,
        "Source URL": url,
        "Site Name": SITE_NAME,
    }

    # 若原价存在，把它附加到 Feature 末尾，不增字段名（与你其它站点的写法一致）
    if orig_price is not None:
        extra = f"Original Price: {orig_price:.2f}"
        info["Feature"] = (info["Feature"] + "; " + extra) if info["Feature"] != "No Data" else extra

    return info


def process_url(url: str):
    print(f"\n🌐 正在抓取: {url}")
    driver = get_driver()
    try:
        driver.get(url)
        time.sleep(2.5)  # 轻等待，视页面复杂度可适当增加
        html = driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    info = parse_and_build_info(html, url)

    # 文件名：HOF 无编码 → 用标题安全化
    safe_name = re.sub(r"[\\/:*?\"<>|'\s]+", "_", info.get("Product Name") or "NoName")
    out_path = TXT_DIR / f"{safe_name}.txt"
    format_txt(info, out_path, brand="Barbour")  # 与 barbour_fetch_info 等保持一致
    print(f"✅ 写入: {out_path.name}")
    return out_path


# ========== 主入口：零参数，读取 config 链接文件 ==========
def houseoffraser_fetch_info():
    links_file = Path(LINKS_FILE)
    if not links_file.exists():
        print(f"⚠ 找不到链接文件：{links_file}")
        return

    urls = [line.strip() for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")]
    print(f"📄 共 {len(urls)} 个商品页面待解析...")

    for idx, url in enumerate(urls, 1):
        try:
            print(f"[{idx}/{len(urls)}] 处理中...")
            process_url(url)
        except Exception as e:
            print(f"❌ 处理失败: {url}\n    {e}")


if __name__ == "__main__":
    houseoffraser_fetch_info()
