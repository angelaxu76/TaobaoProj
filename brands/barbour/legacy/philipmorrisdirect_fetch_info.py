
# -*- coding: utf-8 -*-
"""
Philip Morris Direct | Barbour 商品抓取（最终整合版）

功能：
1. 多线程稳定抓取
2. 自动重建 driver（InvalidSessionId 自动修复）
3. 主 TXT / TXT.problem 分流
4. 自动记录未知颜色 unknown_colors.csv
5. 自动记录所有问题 problem_summary.csv
6. 自动支持颜色前缀去除（Soft Mint → Mint）
7. 完整编码才写入 TXT，不完整写 TXT.problem
8. 提供 generate_color_map_suggestions.py 生成颜色建议
"""

import re
import time
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
import psycopg2

from config import BARBOUR
from common.ingest.txt_writer import format_txt
from typing import List
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
except ImportError:
    def stealth(*args, **kwargs):
        return


#########################################
# 配置与路径
#########################################

LINKS_FILE: Path = BARBOUR["LINKS_FILES"]["philipmorris"]
TXT_DIR: Path = BARBOUR["TXT_DIRS"]["philipmorris"]
SITE_NAME = "Philip Morris"
PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]
COLOR_CODE_MAP = BARBOUR["BARBOUR_COLOR_CODE_MAP"]

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


import re
from typing import List


# ============================================
# 颜色处理：从数据库 barbour_color_map 读取颜色码
# ============================================

import threading
import psycopg2
from typing import List, Dict

# 这里假设文件顶部已经有：
# from config import BARBOUR, PGSQL_CONFIG
# PGSQL_CONFIG 就是连接 PostgreSQL 的 dict

# 全局缓存：归一化后的颜色名 -> 可能的 color_code 列表
_COLOR_MAP_CACHE: Dict[str, List[str]] = {}
_COLOR_MAP_LOADED: bool = False
_COLOR_MAP_LOCK = threading.Lock()


def _normalize_color_tokens(s: str) -> List[str]:
    """
    把颜色名统一成单词列表，用来做“完全同一组单词”的匹配。

    规则：
    - 不关心大小写
    - 把 '/', ',', '&', '-' 等都当成分隔符
    - 只保留 a-z0-9
    - 去掉空单词
    """
    if not s:
        return []

    import re

    s = s.lower()
    # 把各种分隔符先统一成空格
    s = re.sub(r"[\/,&\-]+", " ", s)
    # 去掉其它奇怪符号，只留字母数字和空格
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    tokens = [t for t in s.split() if t]
    return tokens


def _color_key(s: str) -> str:
    """
    把颜色名变成一个“排序后的 token 串”，
    用这个作为字典的 key，保证：
      - 'Oatmeal / Ancient Tartan' 和 'Ancient Tartan Oatmeal' → 同一个 key
      - 'Oatmeal' 和 'Oatmeal / Ancient Tartan' → 不同 key
    """
    tokens = _normalize_color_tokens(s)
    if not tokens:
        return ""
    return " ".join(sorted(tokens))


def _load_color_map_from_db() -> None:
    """
    只在第一次调用时，从 barbour_color_map 表中把所有
    (color_code, raw_name, norm_key, source, is_confirmed) 读出来，
    构建 _COLOR_MAP_CACHE。

    优先级：
      1）source = 'config_code_map' 的记录排在前面
      2）source = 'products' 等其它来源排在后面
    同一个 key 下如果出现重复 color_code，只保留一份。
    """
    global _COLOR_MAP_LOADED, _COLOR_MAP_CACHE

    with _COLOR_MAP_LOCK:
        if _COLOR_MAP_LOADED:
            return

        try:
            conn = psycopg2.connect(**PGSQL_CONFIG)
            cur = conn.cursor()
            # 按 norm_key + source 优先级排序
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
            # norm_key 已经是标准化 key 了，但为安全起见，
            # 如果 norm_key 为空就用 raw_name 现算一遍
            key = norm_key or _color_key(raw_name or "")
            if not key:
                continue

            codes = cache.setdefault(key, [])

            # 去重 + 保证 config_code_map 的优先级
            if color_code in codes:
                continue

            if source == "config_code_map":
                # 人工配置的放前面
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
    """
    一个颜色名 → 可能对应多个颜色码（从 barbour_color_map 表中来）

    匹配规则：
      - 不修改 TXT / config 中的原始颜色字符串；
      - 内部用 _color_key 做“单词集合完全一致”的匹配：
          * 'Navy'            ↔ 'navy'               ✅
          * 'Oatmeal / Ancient Tartan'
              ↔ 'Ancient Tartan Oatmeal'            ✅
          * 'Oatmeal'
              ↔ 'Oatmeal / Ancient Tartan'          ❌（单词数不同）
    """
    if not color:
        return []

    _load_color_map_from_db()
    key = _color_key(color)
    if not key:
        return []

    codes = _COLOR_MAP_CACHE.get(key, [])
    # 调试时可以看一下映射结果
    print(f"🧩 map_color_to_codes: '{color}' (key='{key}') -> {codes}")
    return codes


def map_color_to_code(color: str) -> str | None:
    """
    兼容旧代码：多数地方只需要一个 color_code，
    这里简单取第一个，有多个的时候交给 DB 再筛选。
    """
    codes = map_color_to_codes(color)
    return codes[0] if codes else None



def create_driver(headless=True):
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

    print("🚗 [get_driver] 创建新的 Chrome driver (PhilipMorris)")
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


def get_driver(headless=True):
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
            except:
                pass
        _all_drivers.clear()


#########################################
# 工具函数
#########################################

def accept_cookies(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"))
        ).click()
        time.sleep(1)
    except:
        pass


def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|'\\s]+", "_", (name or "")).strip("_")


#########################################
# 颜色处理（含自动识别前缀）
#########################################

def record_unknown_color(style: str, color: str, url: str):
    from datetime import datetime
    with open(UNKNOWN_COLOR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{style},{color},{url},{datetime.now().isoformat(timespec='seconds')}\n")


def record_problem_item(style, color, product_code, reason, url):
    from datetime import datetime
    with open(PROBLEM_SUMMARY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{style},{color},{product_code},{reason},{url},{datetime.now().isoformat(timespec='seconds')}\n")


#########################################
# 款式编码提取
#########################################

#########################################
# 款式编码提取（含完整 MPN）
#########################################

def extract_full_mpn(html: str) -> str | None:
    """
    从页面 HTML 中尽量抽取完整的 Barbour MPN，例如 MCA1053OL34。
    成功时返回完整编码（含颜色+尺码），失败时返回 None。
    """
    text = html or ""

    # 1) 优先从 "MPN:" 一行中提取
    m = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text)
    if m:
        raw = m.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            # 标准形态：3字母 + 4数字 + 2字母(颜色) + 2~4位尺码数字
            # 例如：MCA1053OL34 / MWX0008NY91
            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", token):
                return token

    # 2) 兜底：在整页里直接找形如 MCA1053OL34 的片段
    m = re.search(r"\b([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})\b", text)
    if m:
        return m.group(1)

    return None


def extract_style_code(html: str) -> str | None:
    """
    提取 7 位款式编码（不含颜色/尺码，例如 MCA1053）。
    如果已经能拿到完整 MPN，则直接截前 7 位。
    """
    text = html or ""

    # ✅ 优先用完整 MPN 截取前 7 位
    full_mpn = extract_full_mpn(text)
    if full_mpn:
        return full_mpn[:7]

    # 下面是原有兜底逻辑，防止某些页面没有完整 MPN
    mpn = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text)
    if mpn:
        raw = mpn.group(1)
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if re.match(r"^[A-Z]{3}\d{4}[A-Z0-9]{0,6}$", token):
                return token[:7]

    m = re.search(r"\b([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})\b", text)
    if m:
        return m.group(1)[:7]

    m = re.search(r"\b([A-Z]{3}\d{4})\b", text)
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


def extract_prices(soup):
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


def extract_sizes(html):
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

    支持“一色多码”：
      例如 'Olive' -> ['OL', 'GN']
      会依次用 MQU0281OL%、MQU0281GN% 去查，
      谁能命中就用谁。
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
        # 先按 COLOR_CODE_MAP 中的顺序尝试所有颜色码
        for abbr in color_codes:
            prefix = f"{style}{abbr}"
            cur.execute(sql, (prefix + "%",))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]

        # 特例：Sage SG → GN（如果 SG 在候选列表里）
        if color.strip().lower() == "sage" and "SG" in color_codes and "GN" not in color_codes:
            alt_prefix = f"{style}GN"
            cur.execute(sql, (alt_prefix + "%",))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]

    print(f"⚠️ 数据库未匹配到：{style} / {color} / codes={color_codes}")
    return None


#########################################
# 主流程：处理单 URL
#########################################

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
            print(f"\n🌐 抓取({attempt+1}/2): {url}")
            driver.get(url)
            accept_cookies(driver)
            time.sleep(2)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            style = extract_style_code(html) or ""
            name = soup.find("h1", class_="productView-title")
            product_name = name.text.strip() if name else "No Data"

            desc = soup.find("div", id="tab-description")
            product_desc = " ".join(desc.stripped_strings) if desc else "No Data"

            base_orig, base_sale = extract_prices(soup)

            # 颜色按钮（如有）
            color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
            variants = []

            # 🔍 尝试从整页拿完整 MPN
            full_mpn = extract_full_mpn(html)
            if full_mpn:
                print(f"🔍 检测到完整 MPN: {full_mpn}")

            if color_elems:
                # 多颜色/单颜色都走一套变体逻辑
                for idx in range(len(color_elems)):
                    # 每次重新抓元素，避免点击后 DOM 变化导致过时引用
                    color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
                    if idx >= len(color_elems):
                        break

                    elem = color_elems[idx]
                    color = elem.text.strip() or (elem.get_attribute("title") or "No Data")

                    print(f"  🎨 {idx+1}/{len(color_elems)}: {color}")

                    if color == "No Data":
                        continue

                    # 点击颜色，等页面更新
                    driver.execute_script("arguments[0].click();", elem)
                    time.sleep(1.3)

                    html_c = driver.page_source
                    soup_c = BeautifulSoup(html_c, "html.parser")

                    orig, sale = extract_prices(soup_c)
                    sizes = extract_sizes(html_c)
                    size_str = build_size_str(sizes)

                    # Adjusted Price：有折扣时用折后价，否则空
                    adjusted = sale if sale and sale != orig else ""

                    variants.append({
                        "_style": style,
                        "Product Name": product_name,
                        "Product Description": product_desc,
                        "Product Color": color,
                        "Product Price": orig or sale or "0",
                        "Adjusted Price": adjusted,
                        "Product Size": size_str,
                        "Site Name": SITE_NAME,
                        "Source URL": url,
                    })

            else:
                # 完全没有颜色按钮，视为单色商品
                print("⚠️ 无颜色选项 → 视为单色")
                color = "No Data"
                sizes = extract_sizes(html)
                size_str = build_size_str(sizes)
                adjusted = base_sale if base_sale != base_orig else ""

                variants.append({
                    "_style": style,
                    "Product Name": product_name,
                    "Product Description": product_desc,
                    "Product Color": color,
                    "Product Price": base_orig or base_sale or "0",
                    "Adjusted Price": adjusted,
                    "Product Size": size_str,
                    "Site Name": SITE_NAME,
                    "Source URL": url,
                })

            #########################
            # 写入 TXT 或 TXT.problem
            #########################

            if not variants:
                print("❌ 无变体 → 跳过")
                return

            # DB connection
            conn = None
            try:
                conn = psycopg2.connect(**PGSQL_CONFIG)
                print("✅ 数据库连接成功")
            except:
                print("⚠️ 数据库连接失败 → 如无完整 MPN，将全部算问题文件")

            # 是否“单色页面”：
            # - 没有颜色按钮
            # - 或者颜色按钮数量 == 1
            single_color_mode = (not color_elems) or (len(color_elems) <= 1)

            for info in variants:
                style = info.pop("_style") or ""
                color = info["Product Color"]

                product_code = None
                reason = ""

                # =========================
                # 优先逻辑：单色页面 + 完整 MPN
                # =========================
                # 仅在“单色页面”使用完整 MPN，避免多色时把一个颜色的编码错用到其他颜色。
                if single_color_mode and full_mpn and re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2,4}$", full_mpn):
                    product_code = full_mpn
                    # 用完整 MPN 时，不需要颜色映射 / DB，也不记录 unknown_color
                    codes_for_color = []
                else:
                    # =========================
                    # 原有逻辑：款式 + 颜色 → DB 匹配
                    # =========================
                    if conn:
                        # 先算出这个颜色对应的所有候选颜色码（用于判断 unknown_color / no_db_match）
                        codes_for_color = map_color_to_codes(color)
                    else:
                        codes_for_color = []

                    if style and conn:
                        product_code = find_product_code_in_db(style, color, conn, url)

                if product_code:
                    # ✅ 找到完整编码（要么来自 MPN，要么来自 DB）
                    target_dir = TXT_DIR
                    info["Product Code"] = product_code
                else:
                    # ❗ 问题文件：没有完整编码，只能用 style 或 UNKNOWN 占位
                    target_dir = TXT_PROBLEM_DIR
                    info["Product Code"] = style or "UNKNOWN"

                    if not codes_for_color:
                        reason = "unknown_color"
                    else:
                        reason = "no_db_match"

                    record_problem_item(style, color, info["Product Code"], reason, url)

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
# 批量入口
#########################################

def philipmorris_fetch_info(max_workers=3):
    print(f"LINKS_FILE = {LINKS_FILE}")
    print(f"TXT_DIR    = {TXT_DIR}")

    urls = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u:
                urls.append(u)

    print(f"🚀 启动 Philip Morris 抓取，总 {len(urls)} 条，线程数={max_workers}")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            futures = [exe.submit(process_url, u, TXT_DIR) for u in urls]
            for _ in as_completed(futures):
                pass
    finally:
        shutdown_all_drivers()
        print("🧹 已关闭所有 driver")


#########################################
# main
#########################################

if __name__ == "__main__":
    philipmorris_fetch_info(max_workers=10)
