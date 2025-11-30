# -*- coding: utf-8 -*-
"""
Philip Morris Direct | Barbour 商品抓取（v3 增强版）

在 v2 基础上增强点：
1. 保留 v2 的 MPN 提取逻辑 (basic)，新增 PLUS 版本做兜底，不影响原有成功案例。
2. PLUS 版本额外支持：
   - MPN: <span>MSH5303PI51, MSH5303BL32</span> 这类带标签形式
   - JSON-LD 里包含 \u00a0 的 "MPN: ..." 字符串
   - MANUFACTURER'S CODESDAC0004BR15 这类紧挨着的文本
3. 多颜色页面：依然逐色点击获取库存/价格，并利用 MPN + 颜色码为每个颜色选择正确的编码 → 多个 TXT。
4. 单色页面：如果有完整 MPN（含 DAC0004BR15 这种），直接用 MPN 写 TXT，不依赖 DB。
5. 若所有网页方法都失败，再使用款式 + 颜色 → color_map + barbour_products 的兜底方案。
"""

import re
import time
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

import psycopg2
from bs4 import BeautifulSoup

from config import BARBOUR
from common_taobao.ingest.txt_writer import format_txt

# selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    InvalidSessionIdException,
    WebDriverException,
)

try:
    from selenium_stealth import stealth
except ImportError:  # noqa: D401
    def stealth(*args, **kwargs):
        return


#########################################
# 配置与路径
#########################################

LINKS_FILE: Path = BARBOUR["LINKS_FILES"]["philipmorris"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["philipmorris"]
SITE_NAME = "Philip Morris"
PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]

TXT_DIR.mkdir(parents=True, exist_ok=True)

TXT_PROBLEM_DIR: Path = TXT_DIR.parent / "TXT.problem"
TXT_PROBLEM_DIR.mkdir(parents=True, exist_ok=True)

UNKNOWN_COLOR_FILE = TXT_DIR.parent / "unknown_colors.csv"
PROBLEM_SUMMARY_FILE = TXT_DIR.parent / "problem_summary.csv"


#########################################
# 浏览器管理：线程局部 driver
#########################################

drivers_lock = threading.Lock()
_all_drivers = set()
thread_local = threading.local()


def create_driver(headless: bool = True):
    """
    创建一个独立 Chrome driver（Philip Morris 专用）
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    print("🚗 [get_driver] 创建新的 Chrome driver (PhilipMorris v3)")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        stealth(
            driver,
            languages=["en-GB", "en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
    except Exception:
        pass

    with drivers_lock:
        _all_drivers.add(driver)

    return driver


def get_driver(headless: bool = True):
    if not hasattr(thread_local, "driver") or thread_local.driver is None:
        thread_local.driver = create_driver(headless=headless)
    return thread_local.driver


def invalidate_current_driver():
    """
    当前线程 driver 崩了 → 移除 + quit + 重建
    """
    d = getattr(thread_local, "driver", None)
    if d:
        with drivers_lock:
            if d in _all_drivers:
                _all_drivers.remove(d)
        try:
            d.quit()
        except Exception:
            pass
    thread_local.driver = None


def shutdown_all_drivers():
    """
    所有线程结束后统一关闭 driver
    """
    with drivers_lock:
        for d in list(_all_drivers):
            try:
                d.quit()
            except Exception:
                pass
        _all_drivers.clear()


#########################################
# 工具函数
#########################################

def accept_cookies(driver, timeout: int = 5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler")
            )
        ).click()
        time.sleep(1)
    except Exception:
        pass


def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", (name or "")).strip("_")


#########################################
# 颜色处理：barbour_color_map 缓存
#########################################

_COLOR_MAP_CACHE: Dict[str, List[str]] = {}
_COLOR_MAP_LOADED: bool = False
_COLOR_MAP_LOCK = threading.Lock()


def _normalize_color_tokens(s: str) -> List[str]:
    if not s:
        return []
    s = s.lower()
    s = re.sub(r"[\/,&\-]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    tokens = [t for t in s.split() if t]
    return tokens


def _color_key(s: str) -> str:
    tokens = _normalize_color_tokens(s)
    if not tokens:
        return ""
    return " ".join(sorted(tokens))


def _load_color_map_from_db() -> None:
    global _COLOR_MAP_LOADED, _COLOR_MAP_CACHE

    with _COLOR_MAP_LOCK:
        if _COLOR_MAP_LOADED:
            return

        try:
            conn = psycopg2.connect(**PGSQL_CONFIG)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT color_code, raw_name, norm_key, source, is_confirmed
                FROM barbour_color_map
                ORDER BY
                    norm_key,
                    CASE
                        WHEN source = 'config_code_map' THEN 0
                        WHEN source = 'products'       THEN 1
                        ELSE 2
                    END,
                    color_code
                """
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:  # noqa: BLE001
            print("⚠️ 从 barbour_color_map 读取颜色映射失败：", e)
            _COLOR_MAP_LOADED = True
            _COLOR_MAP_CACHE = {}
            return

        cache: Dict[str, List[str]] = {}

        for color_code, raw_name, norm_key, source, is_confirmed in rows:
            key = norm_key or _color_key(raw_name or "")
            if not key:
                continue
            codes = cache.setdefault(key, [])
            if color_code in codes:
                continue
            if source == "config_code_map":
                codes.insert(0, color_code)
            else:
                codes.append(color_code)

        _COLOR_MAP_CACHE = cache
        _COLOR_MAP_LOADED = True
        print(
            f"🎨 已从 barbour_color_map 载入 {len(rows)} 条颜色记录，"
            f"归一化 key 数量：{len(cache)}"
        )


def map_color_to_codes(color: str) -> List[str]:
    if not color:
        return []
    _load_color_map_from_db()
    key = _color_key(color)
    if not key:
        return []
    codes = _COLOR_MAP_CACHE.get(key, [])
    print(f"🧩 map_color_to_codes: '{color}' (key='{key}') -> {codes}")
    return codes


def map_color_to_code(color: str) -> Optional[str]:
    codes = map_color_to_codes(color)
    return codes[0] if codes else None


#########################################
# 记录 unknown_color / problem_summary
#########################################

def record_unknown_color(style: str, color: str, url: str):
    from datetime import datetime

    with open(UNKNOWN_COLOR_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{style},{color},{url},"
            f"{datetime.now().isoformat(timespec='seconds')}\n"
        )


def record_problem_item(style, color, product_code, reason, url):
    from datetime import datetime

    with open(PROBLEM_SUMMARY_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{style},{color},{product_code},{reason},"
            f"{url},{datetime.now().isoformat(timespec='seconds')}\n"
        )


#########################################
# 商品编码提取：basic + PLUS
#########################################

def extract_all_mpns_basic(html: str) -> List[str]:
    """
    v2 原有逻辑：提取网页所有可能出现的 Barbour 完整 MPN。
    保持不变，作为 basic 版本。
    """
    if not html:
        return []

    text = html
    results: List[str] = []
    seen = set()

    # 1) 匹配 MPN 列表
    m = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text, re.I)
    if m:
        raw = m.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip().upper()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", token):
                if token not in seen:
                    seen.add(token)
                    results.append(token)

    # 2) MANUFACTURER'S CODES 段
    for m in re.finditer(
        r"MANUFACTURER'?S\s+CODE\S*([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})",
        text,
        re.I,
    ):
        token = m.group(1).upper()
        if token not in seen:
            seen.add(token)
            results.append(token)

    # 3) 全文兜底匹配
    for token in re.findall(r"([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})", text):
        token = token.upper()
        if token not in seen:
            seen.add(token)
            results.append(token)

    return results


def extract_all_mpns_plus(html: str) -> List[str]:
    """
    PLUS 版：在 basic 结果基础上，额外处理：
      - MPN: <span>XXXX, YYYY</span>
      - JSON-LD 里的 "MPN:\u00a0XXXX"
      - MANUFACTURER'S CODESDAC0004BR15 这类紧挨着的情况
    """
    if not html:
        return []

    # 先拿 basic 结果
    base = extract_all_mpns_basic(html)
    seen = set(base)
    results = list(base)

    # 规范化文本：处理 \u00a0 / &nbsp;
    text_norm = (
        html.replace("\\u00a0", " ")
        .replace("&nbsp;", " ")
    )

    # 1) MPN: <span>XXX, YYY</span>
    m = re.search(
        r"MPN:\s*(?:<[^>]*>)*\s*([A-Z0-9,\s]+)</",
        text_norm,
        flags=re.IGNORECASE,
    )
    if m:
        raw = m.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip().upper()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", token):
                if token not in seen:
                    seen.add(token)
                    results.append(token)

    # 2) JSON-LD 里或文本中：MPN: XXX, YYY Colour: ...
    m = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text_norm, re.I)
    if m:
        raw = m.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip().upper()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", token):
                if token not in seen:
                    seen.add(token)
                    results.append(token)

    # 3) MANUFACTURER'S CODES 紧挨着
    for m in re.finditer(
        r"MANUFACTURER'?S\s+CODE\S*([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})",
        text_norm,
        flags=re.IGNORECASE,
    ):
        token = m.group(1).upper()
        if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", token):
            if token not in seen:
                seen.add(token)
                results.append(token)

    # 4) 再做一次全局兜底（在规范化文本上）
    for token in re.findall(r"([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})", text_norm):
        token = token.upper()
        if token not in seen:
            seen.add(token)
            results.append(token)

    if results:
        print(f"🔍 extract_all_mpns_plus: {results}")
    return results


# v3 对外统一使用 PLUS 版本
def extract_all_mpns(html: str) -> List[str]:
    return extract_all_mpns_plus(html)


def extract_full_mpn_basic(html: str) -> Optional[str]:
    """
    兼容旧接口：basic 版本，仅使用 v2 的逻辑。
    """
    mpns = extract_all_mpns_basic(html)
    return mpns[0] if mpns else None


def extract_full_mpn_plus(html: str) -> Optional[str]:
    """
    PLUS 版本：基于 extract_all_mpns_plus。
    """
    mpns = extract_all_mpns_plus(html)
    return mpns[0] if mpns else None


def extract_style_code(html: str) -> Optional[str]:
    """
    提取 7 位款式编码（不含颜色/尺码，例如 MCA1053 / DAC0004）。

    优先级：
      1）extract_full_mpn_basic
      2）extract_full_mpn_plus
      3）原有兜底逻辑（保持兼容）
    """
    text = html or ""

    full_mpn = extract_full_mpn_basic(text)
    if not full_mpn:
        full_mpn = extract_full_mpn_plus(text)

    if full_mpn:
        return full_mpn[:7]

    # 下面是 v2 的兜底逻辑

    mpn = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text, re.I)
    if mpn:
        raw = mpn.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip().upper()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z0-9]{0,6}$", token):
                return token[:7]

    m = re.search(r"([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})", text)
    if m:
        return m.group(1)[:7]

    m = re.search(r"([A-Z]{3}\d{4})", text)
    if m:
        return m.group(1)

    return None


#########################################
# 价格 & 尺码
#########################################

def _clean_price(t: str) -> str:
    if not t:
        return ""
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", t.replace(",", ""))
    return m.group(1) if m else ""


def extract_prices(soup: BeautifulSoup):
    sale = ""
    orig = ""

    for span in soup.select("span.price.price--withTax"):
        sale = _clean_price(span.text)
        break

    for span in soup.select("span.price.price--rrp"):
        orig = _clean_price(span.text)
        break

    if not sale:
        meta = soup.find("meta", {"property": "product:price:amount"})
        if meta:
            sale = meta.get("content") or ""

    if not orig:
        orig = sale

    return orig, sale


def extract_sizes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    labels = soup.select("label.form-option")
    out = []

    for lb in labels:
        classes = lb.get("class", [])
        if "label-img" in classes:
            continue

        span = lb.find("span", class_="form-option-variant")
        if not span:
            continue

        size = span.text.strip()
        stock = "无货" if "unavailable" in classes else "有货"
        out.append((size, stock))

    return out


def build_size_str(sizes):
    order = []
    agg = {}
    for size, st in sizes:
        if size not in agg:
            agg[size] = st
            order.append(size)
        else:
            if st == "有货":
                agg[size] = "有货"
    return ";".join([f"{s}:{agg[s]}" for s in order])


#########################################
# 数据库匹配
#########################################

def find_product_code_in_db(style: str, color: str, conn, url: str):
    """
    通过 款式编码 + 颜色英文，从 barbour_products 中找到真正的 product_code。
    """
    if not style or not color or not conn:
        return None

    color_codes = map_color_to_codes(color)
    if not color_codes:
        print(f"⚠️ 未找到颜色简写映射：{style} / {color}")
        record_unknown_color(style, color, url)
        return None

    sql = """
        SELECT product_code FROM barbour_products
        WHERE product_code ILIKE %s
        ORDER BY product_code
        LIMIT 1
    """

    with conn.cursor() as cur:
        for abbr in color_codes:
            prefix = f"{style}{abbr}"
            cur.execute(sql, (prefix + "%",))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]

        # 特例：Sage SG → GN
        if color.strip().lower() == "sage" and "SG" in color_codes and "GN" not in color_codes:
            alt_prefix = f"{style}GN"
            cur.execute(sql, (alt_prefix + "%",))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]

    print(f"⚠️ 数据库未匹配到：{style} / {color} / codes={color_codes}")
    return None


#########################################
# 多颜色页面：颜色 → MPN 选择
#########################################

def choose_mpn_for_color(
    style: str,
    color: str,
    all_mpns: List[str],
) -> Optional[str]:
    """
    多颜色页面时，给定款式 + 颜色名，从 all_mpns 中挑出对应的完整编码。

    规则：
      1）只考虑以 style 开头的编码
      2）color 通过 map_color_to_codes 映射到颜色码（如 Navy -> ['NY']）
      3）匹配 style + color_code 前缀，例如 MQU0888NY%%
      4）若刚好只有一个候选，则返回
      5）否则，如果 all_mpns 中只有一个以 style 开头的编码，也接受
    """
    if not style or not color or not all_mpns:
        return None

    style = style.upper()
    codes_for_color = map_color_to_codes(color) or []
    if not codes_for_color:
        return None

    candidates: List[str] = []
    for mpn in all_mpns:
        if not mpn.startswith(style):
            continue
        color_code_part = mpn[len(style): len(style) + 2]
        if color_code_part in codes_for_color:
            candidates.append(mpn)

    if len(candidates) == 1:
        return candidates[0]

    same_style = [m for m in all_mpns if m.startswith(style)]
    if len(same_style) == 1:
        return same_style[0]

    return None


#########################################
# 主流程：处理单 URL
#########################################

def process_url(url: str, output_dir: Path):
    """
    处理单个 URL（含自动重试 2 次）
    """
    for attempt in range(2):
        driver = get_driver(headless=True)

        try:
            print(f"\n🌐 [v3] 抓取({attempt+1}/2): {url}")
            driver.get(url)
            accept_cookies(driver)
            time.sleep(2)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # 基础信息
            style = extract_style_code(html) or ""
            name = soup.find("h1", class_="productView-title")
            product_name = name.text.strip() if name else "No Data"

            desc = soup.find("div", id="tab-description")
            product_desc = " ".join(desc.stripped_strings) if desc else "No Data"

            base_orig, base_sale = extract_prices(soup)

            # 整页所有 MPN（可能多色）
            all_mpns = extract_all_mpns(html)

            # 颜色按钮
            color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
            variants = []

            if color_elems:
                # 多颜色：逐个点击颜色
                for idx in range(len(color_elems)):
                    color_elems = driver.find_elements(
                        By.CSS_SELECTOR, "label.form-option.label-img"
                    )
                    if idx >= len(color_elems):
                        break

                    elem = color_elems[idx]
                    color = elem.text.strip() or (elem.get_attribute("title") or "No Data")
                    print(f"  🎨 {idx+1}/{len(color_elems)}: {color}")

                    if color == "No Data":
                        continue

                    driver.execute_script("arguments[0].click();", elem)
                    time.sleep(1.3)

                    html_c = driver.page_source
                    soup_c = BeautifulSoup(html_c, "html.parser")

                    orig, sale = extract_prices(soup_c)
                    sizes = extract_sizes(html_c)
                    size_str = build_size_str(sizes)

                    adjusted = sale if sale and sale != orig else ""

                    variants.append(
                        {
                            "_style": style,
                            "Product Name": product_name,
                            "Product Description": product_desc,
                            "Product Color": color,
                            "Product Price": orig or sale or "0",
                            "Adjusted Price": adjusted,
                            "Product Size": size_str,
                            "Site Name": SITE_NAME,
                            "Source URL": url,
                        }
                    )
            else:
                # 单色
                print("⚠️ 无颜色选项 → 视为单色")
                color = "No Data"
                sizes = extract_sizes(html)
                size_str = build_size_str(sizes)
                adjusted = base_sale if base_sale != base_orig else ""

                variants.append(
                    {
                        "_style": style,
                        "Product Name": product_name,
                        "Product Description": product_desc,
                        "Product Color": color,
                        "Product Price": base_orig or base_sale or "0",
                        "Adjusted Price": adjusted,
                        "Product Size": size_str,
                        "Site Name": SITE_NAME,
                        "Source URL": url,
                    }
                )

            if not variants:
                print("❌ 无变体 → 跳过")
                return

            # 建立 DB 连接
            conn = None
            try:
                conn = psycopg2.connect(**PGSQL_CONFIG)
                print("✅ 数据库连接成功")
            except Exception:
                print("⚠️ 数据库连接失败 → 如无完整编码，将全部算问题文件")

            single_color_mode = (not color_elems) or (len(color_elems) <= 1)

            for info in variants:
                style = info.pop("_style") or ""
                color = info["Product Color"]

                product_code: Optional[str] = None
                reason = ""
                codes_for_color: List[str] = []

                # A) 优先使用网页上能拿到的完整编码
                if single_color_mode and all_mpns:
                    # 单色：直接用第一个 MPN
                    product_code = all_mpns[0]
                    print(f"  ✅ 单色页面使用完整 MPN: {product_code}")
                elif all_mpns:
                    # 多颜色：按颜色选对应 MPN
                    mpn_for_color = choose_mpn_for_color(style, color, all_mpns)
                    if mpn_for_color:
                        product_code = mpn_for_color
                        print(f"  ✅ 多颜色页面：为 {color} 选择 MPN {product_code}")

                # B) A 失败 → 款式 + 颜色 + DB
                if not product_code:
                    if conn:
                        codes_for_color = map_color_to_codes(color)
                    else:
                        codes_for_color = []

                    if style and conn:
                        product_code = find_product_code_in_db(style, color, conn, url)

                # C) 根据是否拿到完整编码决定 TXT 目录
                if product_code:
                    target_dir = TXT_DIR
                    info["Product Code"] = product_code
                else:
                    target_dir = TXT_PROBLEM_DIR
                    info["Product Code"] = style or "UNKNOWN"

                    if not codes_for_color:
                        reason = "unknown_color"
                    else:
                        reason = "no_db_match"

                    record_problem_item(
                        style,
                        color,
                        info["Product Code"],
                        reason,
                        url,
                    )

                fname = sanitize_filename(info["Product Code"]) + ".txt"
                fpath = target_dir / fname
                format_txt(info, fpath, brand="Barbour")

                if target_dir == TXT_DIR:
                    print(f"  ✅ 写入 TXT: {fname}")
                else:
                    print(f"  ⚠️ 写入 TXT.problem: {fname}  ({reason})")

            return  # 本链接成功完成

        except InvalidSessionIdException as e:
            print(f"⚠️ driver 会话失效 → 重建: {e}")
            invalidate_current_driver()
            time.sleep(2)
        except WebDriverException as e:
            print(f"⚠️ WebDriverException（第 {attempt+1} 次）: {e}")
            invalidate_current_driver()
            time.sleep(2)
        except Exception as e:
            print(f"❌ 抓取失败（第 {attempt+1} 次）: {e}")
            traceback.print_exc()
            break

    print(f"❌ 最终失败: {url}")


#########################################
# 批量入口（v3）
#########################################

def philipmorris_fetch_info_v3(max_workers: int = 3):
    print(f"LINKS_FILE = {LINKS_FILE}")
    print(f"TXT_DIR    = {TXT_DIR}")

    urls: List[str] = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u:
                urls.append(u)

    print(
        f"🚀 [v3] 启动 Philip Morris 抓取，总 {len(urls)} 条，线程数={max_workers}"
    )

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            futures = [exe.submit(process_url, u, TXT_DIR) for u in urls]
            for _ in as_completed(futures):
                pass
    finally:
        shutdown_all_drivers()
        print("🧹 已关闭所有 driver")


if __name__ == "__main__":
    # 建议先单测少量链接，再跑全量：
    #   python philipmorrisdirect_fetch_info_v3.py
    philipmorris_fetch_info_v3(max_workers=10)
