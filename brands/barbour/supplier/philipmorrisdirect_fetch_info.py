# -*- coding: utf-8 -*-
"""
Philip Morris Direct 采集器 - Shopify JSON 版

2026-09 站点从 BigCommerce Stencil 主题迁移到 Shopify，旧版依赖的
DOM 选择器 (productView-title / price--withTax / label.form-option 等)
全部失效，且不再需要 Selenium 逐个点击颜色按钮采集。

新逻辑:
- 直接请求 Shopify 公开的 <商品URL>.json 拿标题/描述/颜色尺码 option/
  每个 SKU 的价格与条码
- 结合商品页 HTML 内 <script type="application/ld+json"> 的 offers[]
  (按 sku 给出 InStock/OutOfStock) 得到库存状态
- 数据库反查编码 (barbour_color_map + barbour_products) 与 MPN 提取
  逻辑保持不变 —— 这两者都是基于纯文本正则，与页面主题无关

使用方式:
    python -m brands.barbour.supplier.philipmorrisdirect_fetch_info
"""

from __future__ import annotations

import json
import re
import time
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from common.ingest.txt_writer import format_txt

# 配置
from config import BARBOUR
import psycopg2

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

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


# ================== Shopify 数据获取 ==================

def product_json_url(url: str) -> str:
    """商品页 URL -> Shopify 公开 JSON 接口 URL"""
    base = url.split("?")[0].rstrip("/")
    return base + ".json"


def extract_ld_json_offers(html: str) -> Dict[str, str]:
    """从页面 JSON-LD 中提取 sku -> availability (InStock/OutOfStock)"""
    offers_by_sku: Dict[str, str] = {}
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, flags=re.S
    ):
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        for offer in data.get("offers", []) or []:
            sku = offer.get("sku")
            if sku:
                offers_by_sku[sku] = offer.get("availability", "")
    return offers_by_sku


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
    Philip Morris Direct 采集器 (Shopify JSON 版)

    特点:
    - 纯 HTTP 请求 (<url>.json + 页面 JSON-LD)，不再使用 Selenium
    - MPN 提取 + 数据库兜底 (逻辑不变)
    - 每个颜色生成独立 TXT
    """

    def _fetch_html(self, url: str) -> str:
        """覆盖基类方法 - 不使用，因为我们重写了 fetch_one_product"""
        return ""

    def fetch_one_product(self, url: str, idx: int, total: int):
        """
        覆盖基类方法 - 按颜色分组生成多个 TXT

        流程:
        1. 请求商品页 HTML: 用于 MPN 正则提取 + JSON-LD 库存状态
        2. 请求 <url>.json: 拿标题/描述/options/variants (价格/sku/条码)
        3. 按 Colour option 分组 variants，逐色写 TXT
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"[{idx}/{total}] [{attempt}/{self.max_retries}] 抓取: {url}")

                resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
                resp.raise_for_status()
                html = resp.text

                resp_json = requests.get(product_json_url(url), headers=REQUEST_HEADERS, timeout=20)
                resp_json.raise_for_status()
                product = resp_json.json().get("product") or {}

                if not product or not product.get("variants"):
                    self.logger.warning("商品 JSON 为空或无变体 -> 跳过")
                    return url, False

                style = extract_style_code(html) or ""
                product_name = product.get("title") or "No Data"

                desc_html = product.get("body_html") or ""
                product_desc = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
                product_desc = product_desc.split("Barbour's Ref")[0].strip() or "No Data"

                all_mpns = extract_all_mpns_plus(html)
                gender = self.infer_gender(
                    text=f"{product_name} {product_desc}", url=url, output_format="en"
                )
                availability_by_sku = extract_ld_json_offers(html)

                # 定位 Colour / Size 分别对应 option1/2/3
                color_opt_idx = None
                size_opt_idx = None
                for opt in product.get("options") or []:
                    opt_name = (opt.get("name") or "").strip().lower()
                    if opt_name in ("colour", "color") and color_opt_idx is None:
                        color_opt_idx = opt.get("position")
                    elif opt_name == "size" and size_opt_idx is None:
                        size_opt_idx = opt.get("position")

                variants = product["variants"]

                by_color: Dict[str, List[dict]] = {}
                for v in variants:
                    color = (v.get(f"option{color_opt_idx}") if color_opt_idx else None) or "No Data"
                    by_color.setdefault(color, []).append(v)

                single_color_mode = len(by_color) <= 1

                for color, color_variants in by_color.items():
                    size_detail: Dict[str, Dict] = {}
                    prices: List[tuple] = []  # (float_val, original_str)
                    compare_prices: List[tuple] = []

                    for v in color_variants:
                        size = (v.get(f"option{size_opt_idx}") if size_opt_idx else None) or "One Size"
                        sku = v.get("sku") or ""
                        availability = availability_by_sku.get(sku, "https://schema.org/InStock")
                        stock = self.default_stock if availability.endswith("InStock") else 0
                        ean = v.get("barcode") or "0000000000000"

                        prev = size_detail.get(size)
                        if prev is None or stock > prev["stock_count"]:
                            size_detail[size] = {"stock_count": stock, "ean": ean}

                        if v.get("price"):
                            try:
                                prices.append((float(v["price"]), str(v["price"])))
                            except (TypeError, ValueError):
                                pass
                        if v.get("compare_at_price"):
                            try:
                                compare_prices.append((float(v["compare_at_price"]), str(v["compare_at_price"])))
                            except (TypeError, ValueError):
                                pass

                    product_size, product_size_detail = self.build_size_lines(size_detail, gender)

                    sale_price = min(prices, default=None)
                    orig_price = max(compare_prices, default=None) or sale_price
                    adjusted = ""
                    if sale_price and orig_price and sale_price[0] != orig_price[0]:
                        adjusted = sale_price[1]

                    info: Dict[str, Any] = {
                        "Product Name": product_name,
                        "Product Description": product_desc,
                        "Product Color": color,
                        "Product Gender": gender,
                        "Product Price": orig_price[1] if orig_price else "0",
                        "Adjusted Price": adjusted,
                        "Product Size": product_size,
                        "Product Size Detail": product_size_detail,
                        "Site Name": SITE_NAME,
                        "Source URL": url,
                    }

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

    def _sanitize_filename(self, name: str) -> str:
        """文件名清理"""
        return re.sub(r"[\\/:*?\"<>|\s]+", "_", (name or "")).strip("_")

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        这个方法不会被调用
        因为我们重写了 fetch_one_product
        """
        return {}


# ================== 主入口 ==================

def philipmorris_fetch_info(max_workers: int = 3):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数
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
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Philip Morris 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    philipmorris_fetch_info(max_workers=5)
