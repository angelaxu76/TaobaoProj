# outdoorandcountry_fetch_info.py
# -*- coding: utf-8 -*-

import time
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

from config import BARBOUR
from barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# ⬇️ 统一到“鲸芽/通用”TXT 写入器（与 camper / clarks_jingya 相同）
# 如果你的写入器路径是 txt_writer.py，就改成: from txt_writer import format_txt
from common_taobao.txt_writer import format_txt


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


def _normalize_color_from_url(url: str) -> str:
    """
    解析 ?c= 颜色参数，并规范化：
    - URL 解码（%2F -> /, %20 -> 空格）
    - 压缩多余空白
    - 把斜杠两侧加空格，统一为 ' / '
    - 每个词首字母大写
    """
    try:
        qs = parse_qs(urlparse(url).query)
        c = qs.get("c", [None])[0]
        if not c:
            return ""
        c = unquote(c)
        c = c.replace("\\", "/")
        c = re.sub(r"\s*/\s*", " / ", c)
        c = re.sub(r"\s+", " ", c).strip()
        c = " ".join(w.capitalize() for w in c.split(" "))
        return c
    except Exception:
        return ""


def sanitize_filename(name: str) -> str:
    """将文件名中非法字符替换成下划线，避免创建子目录"""
    return re.sub(r"[\\/:*?\"<>|'\\s]+", "_", (name or "").strip())


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
    Outdoor & Country 的 JSON-LD 里，单个 offer.mpn 形如: MWX0017OL9934
                                    ^^^^ 颜色码（示例 OL99），后面两位为尺码编码。
    这里取末尾 4 位颜色块（OL99）。若要“全码”（如 MWX0017OL99），
    请在 parse_offer_info 里拼接 style code 与此颜色块。
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
                            return m.group(1)  # e.g. "OL99"
        except Exception:
            continue
    return ""


def process_url(url: str, output_dir: Path):
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

        # 颜色名从 URL 兜底（?c= 参数）
        url_color = _normalize_color_from_url(url)

        # 1) 先用你现有解析器拿结构化信息（Offers、标题、颜色、可能的码等）
        info = parse_offer_info(html, url)
        if not isinstance(info, dict):
            info = {}

        # 2) 统一补全字段（与鲸芽模板对齐）
        info.setdefault("Product Name", "No Data")
        # Outdoor 原来多用 "Product Color"；写入器也支持 "Product Colour"，这里两个键都写，最大兼容
        colour = info.get("Product Color") or url_color or "No Data"
        info["Product Color"] = colour
        info["Product Colour"] = colour
        info.setdefault("Site Name", "Outdoor and Country")
        info.setdefault("Source URL", url)
        info.setdefault("Offers", [])

        # 描述 / 卖点 / 性别
        info["Product Description"] = _extract_description(html)
        info["Feature"] = _extract_features(html)
        info["Product Gender"] = _infer_gender_from_name(info.get("Product Name", ""))

        # 颜色编码（用于文件名 & TXT 字段）
        color_code = info.get("Product Color Code") or _extract_color_code_from_jsonld(html)
        if color_code:
            info["Product Color Code"] = color_code

        # 若 parse_offer_info 已解析出“完整商品码（如 MWX0339NY92）”，可写入 Product Code
        # 写入器同时兼容 "Product Code" / "Product Color Code"
        if info.get("Product Code"):
            code_for_file = info["Product Code"]
        elif color_code:
            code_for_file = color_code
        else:
            # 回退：名_色
            safe_name = sanitize_filename(info.get("Product Name", "NoName"))
            safe_color = sanitize_filename(info.get("Product Color", "NoColor"))
            code_for_file = f"{safe_name}_{safe_color}"

        # 3) 统一写 TXT（与 camper/clarks_jingya 完全一致）
        txt_path = output_dir / f"{sanitize_filename(code_for_file)}.txt"
        format_txt(info, txt_path)  # ✅ 统一写入器
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
            pass  # 可加进度或错误收集


if __name__ == "__main__":
    fetch_outdoor_product_offers_concurrent(max_workers=3)
