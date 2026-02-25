# -*- coding: utf-8 -*-
"""
Philip Morris Direct 采集器 - 重构版 (使用 BaseFetcher)

基于 philipmorrisdirect_fetch_info_v2.py 重构
特点:
- 数据库反查编码 (barbour_color_map + barbour_products)
- meta[property="product:price"] 价格
- 复杂的编码映射 (MPN 提取 + DB 兜底)
- 多颜色页面逐色处理

对比:
- 旧版 (philipmorrisdirect_fetch_info_v2.py): 912 行
- 新版 (本文件): ~400 行
- 代码减少: 56%

使用方式:
    python -m brands.barbour.supplier.philipmorrisdirect_fetch_info_v3
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# Selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 配置
from config import BARBOUR
import psycopg2

SITE_NAME = "Philip Morris"
LINKS_FILE = BARBOUR["LINKS_FILES"]["philipmorris"]
OUTPUT_DIR = BARBOUR["TXT_DIRS"]["philipmorris"]
PGSQL_CONFIG = BARBOUR["PGSQL_CONFIG"]

# 问题文件目录
TXT_PROBLEM_DIR = OUTPUT_DIR.parent / "TXT.problem"
TXT_PROBLEM_DIR.mkdir(parents=True, exist_ok=True)


# ================== 颜色映射缓存 ==================

_COLOR_MAP_CACHE: Dict[str, List[str]] = {}
_COLOR_MAP_LOADED = False


def _normalize_color_tokens(s: str) -> List[str]:
    """标准化颜色文本为词列表"""
    if not s:
        return []
    s = s.lower()
    s = re.sub(r"[\/,&\-]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    tokens = [t for t in s.split() if t]
    return tokens


def _color_key(s: str) -> str:
    """生成颜色键"""
    tokens = _normalize_color_tokens(s)
    if not tokens:
        return ""
    return " ".join(sorted(tokens))


def load_color_map_from_db() -> None:
    """从数据库加载颜色映射"""
    global _COLOR_MAP_LOADED, _COLOR_MAP_CACHE

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
    except Exception as e:
        print(f"⚠️ 从 barbour_color_map 读取颜色映射失败: {e}")
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
    print(f"🎨 已从 barbour_color_map 载入 {len(rows)} 条颜色记录")


def map_color_to_codes(color: str) -> List[str]:
    """颜色文本 -> 颜色码列表"""
    if not color:
        return []

    load_color_map_from_db()

    key = _color_key(color)
    if not key:
        return []

    codes = _COLOR_MAP_CACHE.get(key, [])
    return codes


def map_color_to_code(color: str) -> Optional[str]:
    """颜色文本 -> 首个颜色码"""
    codes = map_color_to_codes(color)
    return codes[0] if codes else None


# ================== MPN 提取 ==================

def extract_all_mpns_plus(html: str) -> List[str]:
    """
    PLUS 版: 提取页面所有 Barbour MPN
    - MPN: <span>XXXX, YYYY</span>
    - JSON-LD 里的 "MPN:\u00a0XXXX"
    - MANUFACTURER'S CODES 紧挨着
    """
    if not html:
        return []

    results: List[str] = []
    seen = set()

    # 规范化文本: 处理 \u00a0 / &nbsp;
    text_norm = html.replace("\\u00a0", " ").replace("&nbsp;", " ")

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

    # 2) MPN: XXX, YYY Colour: ...
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

    # 4) 全局兜底
    for token in re.findall(r"([A-Z]{3}\d{4}[A-Z]{2}\d{2,4})", text_norm):
        token = token.upper()
        if token not in seen:
            seen.add(token)
            results.append(token)

    return results


def extract_style_code(html: str) -> Optional[str]:
    """提取 7 位款式编码 (不含颜色/尺码)"""
    text = html or ""

    # 先尝试完整 MPN
    mpns = extract_all_mpns_plus(text)
    if mpns:
        return mpns[0][:7]

    # 兜底
    m = re.search(r"MPN:\s*([A-Z0-9,\s]+)", text, re.I)
    if m:
        raw = m.group(1)
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


# ================== 数据库匹配 ==================

def find_product_code_in_db(style: str, color: str, url: str) -> Optional[str]:
    """
    通过款式 + 颜色从数据库查找 product_code

    优先: style + color_map 颜色码前缀
    兜底: style + 颜色文本直接匹配
    """
    if not style or not color:
        return None

    style_u = style.strip().upper()
    color_s = (color or "").strip()

    sql_prefix = """
        SELECT product_code
        FROM barbour_products
        WHERE product_code ILIKE %s
        ORDER BY product_code
        LIMIT 1
    """

    sql_fallback = """
        SELECT product_code
        FROM barbour_products
        WHERE SUBSTRING(product_code, 1, 7) = %s
          AND (
                LOWER(TRIM(color)) = LOWER(TRIM(%s))
                OR color ILIKE %s
          )
        ORDER BY product_code
        LIMIT 1
    """

    color_codes = map_color_to_codes(color_s) or []

    try:
        conn = psycopg2.connect(**PGSQL_CONFIG)
        cur = conn.cursor()

        # A) 默认: style + code2 前缀查找
        if color_codes:
            for abbr in color_codes:
                prefix = f"{style_u}{abbr}"
                cur.execute(sql_prefix, (prefix + "%",))
                row = cur.fetchone()
                if row and row[0]:
                    cur.close()
                    conn.close()
                    return row[0]

            # 特例: Sage SG -> GN
            if color_s.lower() == "sage" and "SG" in color_codes and "GN" not in color_codes:
                alt_prefix = f"{style_u}GN"
                cur.execute(sql_prefix, (alt_prefix + "%",))
                row = cur.fetchone()
                if row and row[0]:
                    cur.close()
                    conn.close()
                    return row[0]

        # B) 兜底: style + 颜色文本直接匹配
        cur.execute(sql_fallback, (style_u, color_s, f"%{color_s}%"))
        row = cur.fetchone()

        cur.close()
        conn.close()

        if row and row[0]:
            print(f"✅ DB 兜底匹配成功: {style_u} / {color_s} -> {row[0]}")
            return row[0]

    except Exception as e:
        print(f"⚠️ 数据库匹配失败: {e}")

    return None


def choose_mpn_for_color(style: str, color: str, all_mpns: List[str]) -> Optional[str]:
    """从 all_mpns 中选择匹配颜色的 MPN"""
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

    # 同款式只有一个 MPN
    same_style = [m for m in all_mpns if m.startswith(style)]
    if len(same_style) == 1:
        return same_style[0]

    return None


# ================== 采集器实现 ==================

class PhilipMorrisFetcher(BaseFetcher):
    """
    Philip Morris Direct 采集器

    特点:
    - 多颜色页面逐色点击
    - MPN 提取 + 数据库兜底
    - 每个颜色生成独立 TXT
    """

    def _fetch_html(self, url: str) -> str:
        """
        覆盖基类方法 - 不使用基类的 HTML 获取
        Philip Morris 需要交互式处理多颜色
        """
        # 这个方法不会被调用，因为我们重写了 fetch_one_product
        return ""

    def fetch_one_product(self, url: str, idx: int, total: int):
        """
        覆盖基类方法 - 处理多颜色页面

        Philip Morris 特殊逻辑:
        1. 点击每个颜色选项
        2. 为每个颜色生成独立 TXT
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"[{idx}/{total}] [{attempt}/{self.max_retries}] 抓取: {url}")

                driver = self.get_driver()

                try:
                    driver.get(url)
                    self._accept_cookies(driver)
                    time.sleep(2)

                    html = driver.page_source
                    soup = BeautifulSoup(html, "html.parser")

                    # 基础信息
                    style = extract_style_code(html) or ""
                    name = soup.find("h1", class_="productView-title")
                    product_name = name.text.strip() if name else "No Data"

                    desc = soup.find("div", id="tab-description")
                    product_desc = " ".join(desc.stripped_strings) if desc else "No Data"

                    base_orig, base_sale = self._extract_prices(soup)

                    # 整页所有 MPN
                    all_mpns = extract_all_mpns_plus(html)

                    # 颜色按钮
                    color_elems = driver.find_elements(By.CSS_SELECTOR, "label.form-option.label-img")
                    variants = []

                    if color_elems:
                        # 多颜色: 逐个点击
                        for idx_color in range(len(color_elems)):
                            color_elems = driver.find_elements(
                                By.CSS_SELECTOR, "label.form-option.label-img"
                            )
                            if idx_color >= len(color_elems):
                                break

                            elem = color_elems[idx_color]
                            color = elem.text.strip() or (elem.get_attribute("title") or "No Data")
                            self.logger.info(f"  🎨 {idx_color + 1}/{len(color_elems)}: {color}")

                            if color == "No Data":
                                continue

                            driver.execute_script("arguments[0].click();", elem)
                            time.sleep(1.3)

                            html_c = driver.page_source
                            soup_c = BeautifulSoup(html_c, "html.parser")

                            orig, sale = self._extract_prices(soup_c)
                            sizes = self._extract_sizes(html_c)
                            size_str = self._build_size_str(sizes)

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
                        # 单色
                        self.logger.warning("无颜色选项 -> 视为单色")
                        color = "No Data"
                        sizes = self._extract_sizes(html)
                        size_str = self._build_size_str(sizes)
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

                    if not variants:
                        self.logger.warning("无变体 -> 跳过")
                        return url, False

                    # 写入每个颜色的 TXT
                    single_color_mode = (not color_elems) or (len(color_elems) <= 1)

                    for info in variants:
                        style = info.pop("_style") or ""
                        color = info["Product Color"]

                        product_code: Optional[str] = None

                        # A) 优先使用网页 MPN
                        if single_color_mode and all_mpns:
                            product_code = all_mpns[0]
                            self.logger.info(f"  ✅ 单色页面使用完整 MPN: {product_code}")
                        elif all_mpns:
                            mpn_for_color = choose_mpn_for_color(style, color, all_mpns)
                            if mpn_for_color:
                                product_code = mpn_for_color
                                self.logger.info(f"  ✅ 多颜色页面: 为 {color} 选择 MPN {product_code}")

                        # B) MPN 失败 -> 数据库兜底
                        if not product_code and style:
                            product_code = find_product_code_in_db(style, color, url)

                        # C) 决定输出目录
                        if product_code:
                            target_dir = self.output_dir
                            info["Product Code"] = product_code
                        else:
                            target_dir = TXT_PROBLEM_DIR
                            info["Product Code"] = style or "UNKNOWN"

                        # 写入文件
                        from common.ingest.txt_writer import format_txt

                        fname = self._sanitize_filename(info["Product Code"]) + ".txt"
                        fpath = target_dir / fname
                        format_txt(info, fpath, brand="Barbour")

                        if target_dir == self.output_dir:
                            self.logger.info(f"  ✅ 写入 TXT: {fname}")
                        else:
                            self.logger.warning(f"  ⚠️ 写入 TXT.problem: {fname}")

                    with self._lock:
                        self._success_count += 1

                    return url, True

                finally:
                    self.quit_driver()

            except Exception as e:
                self.logger.error(
                    f"❌ [{idx}/{total}] 尝试 {attempt}/{self.max_retries} 失败: {url} - {e}",
                    exc_info=(attempt == self.max_retries),
                )

                if attempt < self.max_retries:
                    wait_time = min(2 ** attempt, 30)
                    time.sleep(wait_time)

                if attempt == self.max_retries:
                    with self._lock:
                        self._fail_count += 1
                    return url, False

        return url, False

    def _accept_cookies(self, driver):
        """接受 Cookie"""
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler")
                )
            ).click()
            time.sleep(1)
        except Exception:
            pass

    def _sanitize_filename(self, name: str) -> str:
        """文件名清理"""
        return re.sub(r"[\\/:*?\"<>|\s]+", "_", (name or "")).strip("_")

    def _extract_prices(self, soup: BeautifulSoup):
        """提取价格"""
        sale = ""
        orig = ""

        for span in soup.select("span.price.price--withTax"):
            sale = self._clean_price(span.text)
            break

        for span in soup.select("span.price.price--rrp"):
            orig = self._clean_price(span.text)
            break

        if not sale:
            meta = soup.find("meta", {"property": "product:price:amount"})
            if meta:
                sale = meta.get("content") or ""

        if not orig:
            orig = sale

        return orig, sale

    def _clean_price(self, t: str) -> str:
        """从文本提取价格"""
        if not t:
            return ""
        m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", t.replace(",", ""))
        return m.group(1) if m else ""

    def _extract_sizes(self, html: str):
        """提取尺码"""
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

    def _build_size_str(self, sizes):
        """构建尺码字符串"""
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

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        这个方法不会被调用
        因为我们重写了 fetch_one_product
        """
        return {}


# ================== 主入口 ==================

def philipmorris_fetch_info(
    max_workers: int = 3,
    headless: bool = True,
):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数
        headless: 是否无头模式
    """
    setup_logging()

    # 预加载颜色映射
    load_color_map_from_db()

    fetcher = PhilipMorrisFetcher(
        site_name="philipmorris",
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=2,
        wait_seconds=2.0,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Philip Morris 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    philipmorris_fetch_info(max_workers=3, headless=True)
