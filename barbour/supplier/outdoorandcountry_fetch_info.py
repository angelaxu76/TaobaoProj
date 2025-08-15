import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import undetected_chromedriver as uc
from config import BARBOUR
from barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info
from barbour.barbouir_write_offer_txt import write_supplier_offer_txt

def accept_cookies(driver, timeout=8):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except:
        pass

import re


from urllib.parse import urlparse, parse_qs, unquote

def _normalize_color_from_url(url: str) -> str:
    """
    解析 ?c= 颜色参数，并规范化：
    - URL 解码（%2F -> /, %20 -> 空格）
    - 压缩多余空白
    - 把斜杠两侧加空格，统一为 ' / '
    - 首字母大写每个词，便于匹配站点显示颜色
    """
    try:
        qs = parse_qs(urlparse(url).query)
        c = qs.get("c", [None])[0]
        if not c:
            return ""
        c = unquote(c)              # %2F -> /
        c = c.replace("\\", "/")
        c = re.sub(r"\s*/\s*", " / ", c)   # 两侧留空格
        c = re.sub(r"\s+", " ", c).strip()
        c = " ".join(w.capitalize() for w in c.split(" "))
        return c
    except Exception:
        return ""


def sanitize_filename(name: str) -> str:
    """将文件名中非法字符替换成下划线，确保不会创建子目录"""
    return re.sub(r"[\\/:*?\"<>|'\s]+", "_", name.strip())

import re
from bs4 import BeautifulSoup

def _extract_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        # 去掉 <br> 的实体
        desc = tag["content"].replace("<br>", "").replace("<br/>", "").replace("<br />", "")
        return desc.strip()
    # 兜底：有些页签里也有 Description 文本
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

def _infer_gender_from_name(name: str) -> str:
    n = (name or "").lower()
    if any(x in n for x in ["men", "men's", "mens"]):
        return "男款"
    if any(x in n for x in ["women", "women's", "womens", "ladies", "lady"]):
        return "女款"
    if any(x in n for x in ["kid", "kids", "child", "children", "boys", "girls", "boy's", "girl's"]):
        return "童款"
    return "未知"

def _extract_color_code_from_jsonld(html: str) -> str:
    """
    期望 mpn 形如: MWX0017OL9934
                         ^^^^ 为颜色码，末尾两位为尺码
    正则: 捕获最后 4 位字母数字块 ([A-Z]{2}\d{2}), 且其后紧跟 2 位尺码数字。
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
                        m = re.search(r'([A-Z]{2}\d{2})(\d{2})$', mpn)
                        if m:
                            return m.group(1)  # e.g. OL99
        except Exception:
            continue
    return ""

def process_url(url, output_dir):
    import json
    import undetected_chromedriver as uc

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


        url_color = _normalize_color_from_url(url)

        # 先跑你现有的解析（包含 Offers、Product Name、Color 等）
        info = parse_offer_info(html, url)

        if not isinstance(info, dict):
            info = {}

        info.setdefault("Product Name", "No Data")
        info.setdefault("Product Color", url_color or "No Data")
        info.setdefault("Site Name", "Outdoor and Country")
        info.setdefault("Product URL", url)
        info.setdefault("Offers", [])
        # --- 新增补全字段 ---
        # 描述
        info["Product Description"] = _extract_description(html)
        # Feature
        info["Feature"] = _extract_features(html)
        # 性别
        info["Product Gender"] = _infer_gender_from_name(info.get("Product Name", ""))

        # 颜色编码（用于文件名 & 写入文本：Product Color Code）
        # --- 新增/确保拿到颜色编码 ---
        color_code = info.get("Product Color Code") or _extract_color_code_from_jsonld(html)
        if color_code:
            info["Product Color Code"] = color_code  # 确保写入到TXT里

        # --- 用 Product Color Code 命名文件；没有再回退到 名称_颜色 ---
        if color_code:
            filename = f"{sanitize_filename(color_code)}.txt"
        else:
            safe_name = sanitize_filename(info.get('Product Name', 'NoName'))
            safe_color = sanitize_filename(info.get('Product Color', 'NoColor'))
            filename = f"{safe_name}_{safe_color}.txt"

        filepath = output_dir / filename
        write_supplier_offer_txt(info, filepath)
        print(f"✅ 写入: {filepath.name}")

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

        for future in as_completed(futures):
            pass  # 可添加进度显示或异常捕获

if __name__ == "__main__":
    fetch_outdoor_product_offers_concurrent(max_workers=3)

