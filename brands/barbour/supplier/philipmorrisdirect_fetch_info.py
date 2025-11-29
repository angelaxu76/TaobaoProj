# -*- coding: utf-8 -*-
"""
Philip Morris Direct | Barbour 商品抓取（支持多颜色、多 TXT、颜色编码映射）

核心逻辑：
1. Selenium 打开商品页，识别所有颜色选项（label.form-option.label-img）
2. 对每个颜色：
   - 点击该颜色
   - 抓取当前页面上的尺码 & 库存（有货/无货）
   - 组合成 Product Size: "S:有货;M:无货;..."
3. 从 HTML 中提取 Barbour 款式编码（如 MQU0281）
4. 用 颜色英文 -> 颜色简写（BK/NY/OL/SG...）得到组合前缀：MQU0281OL
5. 去 PostgreSQL 的 barbour_products 表查：
   SELECT product_code
   FROM barbour_products
   WHERE product_code ILIKE 'MQU0281OL%'
   LIMIT 1
   若找到，用该 product_code 作为：
       - TXT 文件名（MQU0281OL51.txt）
       - TXT 中的 Product Code
   若找不到，则降级用 MQU0281OL 作为 Product Code
6. 所有字段统一写入 info dict，最后用 txt_writer.format_txt(info, filepath, brand="Barbour")
"""

import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import psycopg2
import tempfile
from config import BARBOUR
from common_taobao.ingest.txt_writer import format_txt
from selenium import webdriver
try:
    from selenium_stealth import stealth
except ImportError:
    def stealth(*args, **kwargs):
        return

# ========== 配置 ==========
LINKS_FILE: Path = BARBOUR["LINKS_FILES"]["philipmorris"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["philipmorris"]
SITE_NAME = "Philip Morris"
PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]
COLOR_CODE_MAP = BARBOUR.get("BARBOUR_COLOR_CODE_MAP", {})

TXT_DIR.mkdir(parents=True, exist_ok=True)


# ========== 浏览器 ==========

from common_taobao.core.selenium_utils import get_driver as get_shared_driver

def get_driver(headless: bool = True):
    """
    使用项目统一的 selenium_utils.get_driver（全局共享 chromedriver）
    已经不再使用 build_uc_driver / undetected_chromedriver。
    """
    print("🚗 [get_driver] 调用全局 selenium_utils.get_driver() ...")
    driver = get_shared_driver(
        name="philipmorris",
        headless=headless,
        window_size="1920,1080"
    )
    return driver



def accept_cookies(driver, timeout: int = 8):
    """尽量点掉弹出的 cookie 弹窗，不影响正常运行，失败就忽略。"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except Exception:
        # 有些页面可能是别的 cookie 样式，先忽略
        pass


# ========== 工具函数 ==========

def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|'\s]+", "_", (name or "")).strip("_")


def extract_style_code(html: str) -> str | None:
    """从整页 HTML 中提取 Barbour 款式编码：三字母 + 四数字，如 MQU0281。"""
    m = re.search(r"\b[A-Z]{3}\d{4}\b", html)
    return m.group(0) if m else None


def _clean_price_text(text: str) -> str:
    """从 '£179.00' 之类的字符串中提取出数字部分 '179.00'。"""
    if not text:
        return ""
    t = text.strip()
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", t.replace(",", ""))
    return m.group(1) if m else ""


def extract_prices_pmd(soup: BeautifulSoup) -> tuple[str, str]:
    """
    返回 (原价, 打折价)，都为字符串，例如: ('179.00', '142.95')
    如果没有打折，则两个值相同；如果某个取不到，用另一个兜底。
    """
    sale = ""   # 打折后价
    orig = ""   # 原价 / RRP

    # 打折后价：span.price.price--withTax
    for span in soup.select("span.price.price--withTax"):
        val = _clean_price_text(span.get_text())
        if val:
            sale = val
            break

    # 原价 / RRP：span.price.price--rrp
    for span in soup.select("span.price.price--rrp"):
        val = _clean_price_text(span.get_text())
        if val:
            orig = val
            break

    # 兜底：如果打折价没拿到，用 meta 里的 price amount
    if not sale:
        meta = soup.find("meta", {"property": "product:price:amount"})
        if meta and meta.get("content"):
            sale = meta["content"].strip()

    # 再兜底：如果原价没拿到，就等于当前售价
    if not orig:
        orig = sale

    return orig, sale


# def extract_price(soup: BeautifulSoup) -> str:
#     """从 meta 标签提取价格，GBP 金额，找不到返回 '0.00'。"""
#     meta = soup.find("meta", {"property": "product:price:amount"})
#     if meta and meta.get("content"):
#         return meta["content"].strip()
#     return "0.00"


def extract_product_name(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1", class_="productView-title")
    if h1 and h1.text.strip():
        return h1.text.strip()
    # 兜底用 <title>
    title = soup.find("title")
    if title and title.text:
        return title.text.split("|")[0].strip()
    return "No Data"


def extract_description(soup: BeautifulSoup) -> str:
    """尽量取 Description tab 的文字；失败就返回 'No Data'。"""
    desc = soup.find("div", id="tab-description")
    if not desc:
        desc = soup.find("div", class_="productView-description")
    if not desc:
        return "No Data"
    text = " ".join(desc.stripped_strings)
    return text or "No Data"


def infer_gender(product_name: str) -> str:
    """极简性别推断：识别 Men's / Ladies / Women's，否则默认 Men。"""
    name = (product_name or "").lower()
    if any(w in name for w in ["women", "woman", "ladies", "lady", "women's", "woman's"]):
        return "Women"
    if any(w in name for w in ["men", "men's", "man's"]):
        return "Men"
    return "Men"  # Barbour 外套默认按男款兜底，对你影响不大


def parse_sizes_from_html(html: str) -> list[tuple[str, str]]:
    """
    从当前颜色对应页面解析尺码 + 库存状态
    返回列表: [(size_text, '有货'/'无货'), ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    labels = soup.select("label.form-option")
    sizes: list[tuple[str, str]] = []

    for label in labels:
        classes = label.get("class", [])
        # 过滤颜色按钮（有 label-img）
        if "label-img" in classes:
            continue
        span = label.find("span", class_="form-option-variant")
        if not span:
            continue
        size_text = span.text.strip()
        stock_status = "无货" if "unavailable" in classes else "有货"
        sizes.append((size_text, stock_status))
    return sizes


def build_product_size_str(sizes: list[tuple[str, str]]) -> str:
    """
    把 [(size, status), ...] 聚合成:
        "S:有货;M:无货;..."
    同一尺码多次出现时，只要有一个“有货”就算有货。
    """
    agg = {}
    order = []
    for size, status in sizes:
        if size not in agg:
            agg[size] = status
            order.append(size)
        else:
            # 只要任意一个有货，就认为有货
            if status == "有货" or agg[size] == "有货":
                agg[size] = "有货"
            else:
                agg[size] = "无货"

    tokens = [f"{s}:{agg[s]}" for s in order]
    return ";".join(tokens)


def map_color_to_code(color_name: str) -> str | None:
    """
    用 BARBOUR_COLOR_CODE_MAP 把英文颜色映射到简写：
    - 例如 'Black' -> 'BK'
    - 支持 'Beige/Antique White' 这种，取第一个颜色
    """
    if not color_name:
        return None
    s = color_name.strip().lower()
    # 组合色只取第一个
    if "/" in s:
        s = s.split("/")[0].strip()

    for code, names in COLOR_CODE_MAP.items():
        en = (names.get("en") or "").lower()
        if not en:
            continue
        # 全等 / 包含任意一种情况都算匹配
        if s == en or s in en or en in s:
            return code
    return None


def find_product_code_in_db(style_code: str, color_name: str, conn) -> str | None:
    """
    通过 款式编码 + 颜色英文，从 barbour_products 中找到“真正的商品编码”：
        style_code + color_code_abbr + 尺码后缀
    例如: MQU0281 + OL -> 匹配 MQU0281OL51
    """
    if not style_code or not color_name or conn is None:
        return None

    color_abbr = map_color_to_code(color_name)
    if not color_abbr:
        print(f"⚠️ 未找到颜色简写映射：style={style_code}, color={color_name}")
        return None

    sql = """
        SELECT product_code
        FROM barbour_products
        WHERE product_code ILIKE %s
        ORDER BY product_code
        LIMIT 1
    """

    # ===== 第一次：用正常的颜色简写，例如 Sage -> SG =====
    prefix = f"{style_code}{color_abbr}"
    with conn.cursor() as cur:
        cur.execute(sql, (prefix + "%",))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]

    # ===== 特例处理：Sage 先 SG，没命中再试 GN =====
    # 逻辑：Powell 这种非油蜡，Barbour 官方用 GN；油蜡款才更多用 SG
    if color_name.strip().lower() == "sage" and color_abbr.upper() == "SG":
        alt_abbr = "GN"
        alt_prefix = f"{style_code}{alt_abbr}"
        with conn.cursor() as cur:
            cur.execute(sql, (alt_prefix + "%",))
            row = cur.fetchone()
            if row and row[0]:
                print(f"🔁 Sage 颜色使用 GN 备选简写命中: {alt_prefix} -> {row[0]}")
                return row[0]

    # ===== 仍然没找到，最后兜底：返回原来的前缀 =====
    print(f"⚠️ 数据库中未匹配到 product_code，使用前缀代替: {prefix}")
    return prefix



# ========== 单个链接处理 ==========

def process_url(url: str, output_dir: Path):
    driver = get_driver(headless=True)

    if driver is None:
        print(f"❌ 无法创建浏览器，跳过此链接：{url}")
        return
    try:
        print(f"\n🌐 正在抓取: {url}")
        driver.get(url)
        accept_cookies(driver)
        time.sleep(3)

        html0 = driver.page_source
        soup0 = BeautifulSoup(html0, "html.parser")

        # ---- 公共信息（对所有颜色通用）----
        style_code = extract_style_code(html0) or ""
        product_name = extract_product_name(soup0)
        product_desc = extract_description(soup0)
        base_orig_price, base_sale_price = extract_prices_pmd(soup0)  # 🆕
        gender = infer_gender(product_name)

        # ---- 找到所有颜色按钮 ----
        color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
        if not color_elems:
            print("⚠️ 未找到颜色选项，只按单一颜色处理")
        variants: list[dict] = []

        if color_elems:
            color_count = len(color_elems)
            for idx in range(color_count):
                # 每轮重新获取元素，避免 stale element
                color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
                elem = color_elems[idx]
                color_name = elem.text.strip()
                if not color_name:
                    # 有些样式可能放在 title 里
                    color_name = (elem.get_attribute("title") or "").strip() or "No Data"

                print(f"  🎨 颜色 {idx + 1}/{color_count}: {color_name}")

                if color_name == "No Data":
                    print(f"  ⚠️ 跳过无效颜色选项（index={idx + 1}）")
                    continue

                # 点击该颜色，让页面刷新当前库存
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(1.5)

                html_color = driver.page_source
                soup_color = BeautifulSoup(html_color, "html.parser")

                # 当前颜色价格（同时取原价 & 折后价）
                orig_price, sale_price = extract_prices_pmd(soup_color)

                # 兜底：如果这次没取到，用全局的
                if not sale_price:
                    sale_price = base_sale_price
                if not orig_price:
                    orig_price = base_orig_price or sale_price

                sizes = parse_sizes_from_html(html_color)
                product_size_str = build_product_size_str(sizes)

                # 决定写入 TXT 的两个价格字段：
                # - Product Price = 原价
                # - Adjusted Price = 折后价（只有折扣时填写）
                adjusted_price = ""
                if sale_price and orig_price and sale_price != orig_price:
                    adjusted_price = sale_price

                info = {
                    "Brand": "Barbour",
                    "Product Name": product_name,
                    "Product Description": product_desc,
                    "Product Gender": gender,
                    "Product Color": color_name,
                    "Product Price": orig_price or sale_price or "0.00",
                    "Adjusted Price": adjusted_price,
                    "Product Material": "",
                    "Style Category": "",
                    "Feature": "",
                    "Product Size": product_size_str,
                    "Site Name": SITE_NAME,
                    "Source URL": url,
                    "_style_code": style_code,
                }

                variants.append(info)
        else:
            # 没有颜色选项时，按单一颜色处理
            color_name = "No Data"
            sizes = parse_sizes_from_html(html0)
            product_size_str = build_product_size_str(sizes)

            orig_price, sale_price = base_orig_price, base_sale_price
            adjusted_price = ""
            if sale_price and orig_price and sale_price != orig_price:
                adjusted_price = sale_price

            info = {
                "Brand": "Barbour",
                "Product Name": product_name,
                "Product Description": product_desc,
                "Product Gender": gender,
                "Product Color": color_name,
                "Product Price": orig_price or sale_price or "0.00",
                "Adjusted Price": adjusted_price,
                "Product Material": "",
                "Style Category": "",
                "Feature": "",
                "Product Size": product_size_str,
                "Site Name": SITE_NAME,
                "Source URL": url,
                "_style_code": style_code,
            }


            variants.append(info)

              # ---- 第二阶段：根据 style + 颜色 去数据库找“真正商品编码”，再统一写 TXT ----
        if not variants:
            print("❌ 未解析到任何颜色变体，跳过此链接")
            return

        conn = None
        try:
            # 先尝试连接数据库
            try:
                conn = psycopg2.connect(**PGSQL_CONFIG)
                print("✅ 数据库连接成功")
            except Exception as e:
                print(f"⚠️ 数据库连接失败，将跳过编码精确匹配：{e}")
                conn = None

            for info in variants:
                style_code = info.get("_style_code") or ""
                color_name = info.get("Product Color") or ""
                product_code = None

                # 只有在 style_code 和 conn 都存在时才去 DB 里查
                if style_code and conn is not None:
                    product_code = find_product_code_in_db(style_code, color_name, conn)

                # 查不到 / DB 不通 都兜底用 style_code
                if not product_code:
                    product_code = style_code or "UNKNOWN"

                info["Product Code"] = product_code
                # 清理内部字段
                info.pop("_style_code", None)

                filename = sanitize_filename(product_code) + ".txt"
                txt_path = output_dir / filename
                format_txt(info, txt_path, brand="Barbour")
                print(f"  ✅ 写入 TXT: {txt_path.name}")
        finally:
            if conn is not None:
                conn.close()


    except Exception as e:
        print(f"❌ 处理失败: {url}\n    {e}")
    finally:
        driver.quit()


# ========== 多线程入口 ==========

def philipmorris_fetch_info(max_workers: int = 3):
    print(f"LINKS_FILE = {LINKS_FILE}")
    print(f"TXT_DIR    = {TXT_DIR}")

    urls: list[str] = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                urls.append(url)

    print(f"🚀 Philip Morris 抓取启动，总链接数: {len(urls)}，并发线程数: {max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_url, url, TXT_DIR) for url in urls]
        for _ in as_completed(futures):
            pass


# 兼容之前可能使用的函数名
def fetch_all():
    philipmorris_fetch_info(max_workers=1)


if __name__ == "__main__":
    philipmorris_fetch_info(max_workers=1)
