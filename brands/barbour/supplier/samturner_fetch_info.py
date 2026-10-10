# -*- coding: utf-8 -*-
"""
Sam Turner (sam-turner.co.uk) 采集器

站点特点 (Shopify):
- 用普通 requests + 浏览器 UA 即可访问, 无需 Selenium
- 每个商品详情页有对应的干净 JSON 接口:
    https://www.sam-turner.co.uk/products/<handle>.js
- Barbour 官方编码直接嵌在 variant sku 里, 如 "BB-MWX0010OL7136"
  (前缀 "BB-" + 11 位官方编码 "MWX0010OL71" + 尺码 "36"), 与页面上可见的
  "MPN: MWX0010OL71" / <meta itemprop="mpn"> 完全一致, 用正则直接摘取即可,
  不需要像 williampowell 那样跑数据库模糊匹配
- ⚠️ 特殊之处: 该站不少商品把同一款式的多个颜色放在同一个商品页里
  (variants 里混着不同 Colour, 每个颜色对应不同的官方编码)。
  一个 URL 可能要拆成多个 Product Code 分别写 TXT —— 用 "_extra_records"
  把同一页面解析出的其余颜色记录挂在主记录上, 由重写的 _write_output 统一落盘

使用方式:
    python -m brands.barbour.supplier.samturner_fetch_info
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging
from brands.barbour.core.text_utils import safe_filename
from brands.barbour.supplier.samturner_get_links import PAGE_INTERVAL
from brands.barbour.supplier.samturner_get_links import _fetch_page as _fetch_collection_page
from common.ingest.txt_writer import format_txt

from config import BARBOUR, SETTINGS

SITE_NAME = "samturner"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

_CODE_IN_SKU_RE = re.compile(r"[A-Z]{2,3}\d{4}[A-Z]{2}\d{2}")


def _to_price(pence: Any) -> Optional[float]:
    try:
        v = float(pence)
    except (TypeError, ValueError):
        return None
    return round(v / 100.0, 2)


def _extract_code_from_sku(sku: str) -> str:
    m = _CODE_IN_SKU_RE.search((sku or "").upper())
    return m.group(0) if m else ""


def _gbp_to_pence(value: Any) -> Optional[int]:
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _collection_product_to_js(p: Dict[str, Any]) -> Dict[str, Any]:
    """collection products.json 的商品对象 (价格为英镑字符串, option1/2/3) → 单品 .js 接口结构"""
    options = p.get("options") or []
    n_opts = len(options)
    return {
        "title": p.get("title"),
        "description": p.get("body_html") or "",
        "options": [{"name": o.get("name")} for o in options],
        "variants": [
            {
                "title": v.get("title"),
                "options": [v.get(f"option{i}") for i in range(1, n_opts + 1)],
                "sku": v.get("sku"),
                "available": v.get("available"),
                "barcode": v.get("barcode"),
                "price": _gbp_to_pence(v.get("price")),
                "compare_at_price": _gbp_to_pence(v.get("compare_at_price")),
            }
            for v in p.get("variants") or []
        ],
    }


class SamTurnerFetcher(BaseFetcher):
    """Sam Turner 采集器 - requests 抓取 Shopify .js 接口, SKU 直接给官方编码"""

    _REQ_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/html,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }

    # 单品 .js 回退请求的全局节流 (多线程共用)
    _MIN_REQUEST_INTERVAL = 2.0
    _rate_lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(self._REQ_HEADERS)

        # 单品 .js 接口限流极严 (几十次请求后整个 IP 429 60s),
        # 而 collection products.json 每页 250 条且字段齐全, 先整体拉取作为主数据源
        self._collection_cache = self._load_collection_cache()

    def _load_collection_cache(self) -> Dict[str, Dict[str, Any]]:
        """拉取整个 collection, 转换成与单品 .js 接口相同的结构, 按 handle 索引"""
        session = requests.Session()
        cache: Dict[str, Dict[str, Any]] = {}
        page = 1
        try:
            while True:
                products = _fetch_collection_page(session, page)
                if not products:
                    break
                for p in products:
                    handle = (p.get("handle") or "").strip()
                    if handle:
                        cache[handle] = _collection_product_to_js(p)
                page += 1
                time.sleep(PAGE_INTERVAL)
        except Exception as e:
            self.logger.warning(f"⚠️ collection products.json 拉取中断 (page={page}): {e}, 未命中的商品将回退单品接口")
        self.logger.info(f"📦 collection 缓存: {len(cache)} 个商品")
        return cache

    def _throttle(self) -> None:
        cls = SamTurnerFetcher
        with cls._rate_lock:
            now = time.monotonic()
            wait = cls._last_request_at + cls._MIN_REQUEST_INTERVAL - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            cls._last_request_at = now

    def _fetch_html(self, url: str) -> str:
        """优先使用 collection 缓存; 未命中才请求单品 .js 接口"""
        handle = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].removesuffix(".js")
        cached = self._collection_cache.get(handle)
        if cached is not None:
            return json.dumps(cached)

        js_url = url.rstrip("/") + ".js"
        for attempt in range(1, 4):
            self._throttle()
            # Shopify 对带 _shopify_essential cookie 的后续请求直接 429，每次请求前清空 cookie
            self._session.cookies.clear()
            resp = self._session.get(js_url, timeout=20)
            if resp.status_code != 429:
                break

            try:
                wait = float(resp.headers.get("Retry-After") or 0)
            except ValueError:
                wait = 0.0
            wait = max(wait, 10.0 * attempt)
            self.logger.warning(f"  ⏳ 429 限流, 等待 {wait:.0f}s 后重试 ({attempt}/3): {url}")
            time.sleep(wait)
            with SamTurnerFetcher._rate_lock:
                SamTurnerFetcher._last_request_at = time.monotonic()

        resp.raise_for_status()
        return resp.text

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        data = json.loads(html)

        base_title = data.get("title") or "No Data"
        desc_html = data.get("description") or ""
        description = self.clean_description(
            BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
        )

        options = data.get("options") or []
        color_idx = next(
            (i for i, o in enumerate(options) if any(k in (o.get("name") or "").lower() for k in ("colour", "color"))),
            None,
        )
        size_idx = next(
            (i for i, o in enumerate(options) if "size" in (o.get("name") or "").lower()),
            None,
        )

        # 按 (颜色对应的) Barbour 编码分组: 同一页面不同颜色 = 不同编码 = 不同 TXT
        groups: Dict[str, Dict[str, Any]] = {}
        for v in data.get("variants") or []:
            v_opts = v.get("options") or []
            color = (v_opts[color_idx] if color_idx is not None and color_idx < len(v_opts) else None) or "No Data"
            size_label = (
                (v_opts[size_idx] if size_idx is not None and size_idx < len(v_opts) else None)
                or v.get("title")
                or "One Size"
            )

            code = _extract_code_from_sku(v.get("sku") or "")
            group_key = code or f"__NOCODE__:{color}"

            g = groups.setdefault(group_key, {"code": code, "color": color, "sizes": {}})
            in_stock = bool(v.get("available"))
            g["sizes"][size_label] = {
                "stock_count": DEFAULT_STOCK_COUNT if in_stock else 0,
                "ean": v.get("barcode") or "0000000000000",
            }
            g.setdefault("current_price", _to_price(v.get("price")))
            g.setdefault("original_price", _to_price(v.get("compare_at_price")) or g.get("current_price"))

        if not groups:
            raise ValueError(f"未解析到任何 variant: {url}")

        records: List[Dict[str, Any]] = []
        for g in groups.values():
            color = g["color"]
            name = f"{base_title} - {color}" if color and color != "No Data" else base_title
            gender = self.infer_gender(
                text=name,
                url=url,
                product_code=g["code"] or "",
                output_format="cn",
            )
            product_size, product_size_detail = self.build_size_lines(g["sizes"], gender)

            records.append({
                "Product Code": g["code"] or "No Data",
                "Product Name": self.clean_text(name, maxlen=200),
                "Product Description": description,
                "Product Gender": gender,
                "Product Color": self.clean_text(color, maxlen=100),
                "Product Price": g.get("original_price"),
                "Adjusted Price": g.get("current_price"),
                "Product Material": "No Data",
                "Feature": "No Data",
                "Product Size": product_size,
                "Product Size Detail": product_size_detail,
            })

        primary, *extra = records
        if extra:
            primary["_extra_records"] = extra
        return primary

    def _validate_info(self, info: Dict[str, Any], url: str) -> None:
        required_fields = [
            "Product Code",
            "Product Name",
            "Product Gender",
            "Product Description",
            "Product Size",
            "Product Size Detail",
        ]
        for field in required_fields:
            if field not in info:
                raise ValueError(f"缺失必填字段: {field} (URL: {url})")

    def _write_output(self, info: Dict[str, Any]) -> None:
        """
        重写: 一个 URL 可能拆分出多条记录 (同页多颜色), 逐条落盘。
        没提取到编码的记录用 "URL + 颜色" 计算文件名兜底, 避免同一 URL
        产生多个 "No Data" 记录时互相覆盖 (基类只按 URL 哈希兜底文件名)。
        """
        extra = info.pop("_extra_records", None) or []
        records = [info] + extra

        for rec in records:
            rec.setdefault("Site Name", self.site_name)
            rec.setdefault("Source URL", info.get("Source URL", ""))

            code = (rec.get("Product Code") or "").strip()
            if not code or code in ("Unknown", "No Data", "N/A"):
                key = f"{rec.get('Source URL', '')}|{rec.get('Product Color', '')}"
                safe_code = f"NoCode_{abs(hash(key)) & 0xFFFFFFFF:08x}"
            else:
                safe_code = safe_filename(code)

            txt_path = self.output_dir / f"{safe_code}.txt"
            try:
                format_txt(rec, txt_path, brand="barbour")
            except Exception as e:
                self.logger.error(f"文件写入失败 {txt_path}: {e}")
                raise


def samturner_fetch_info(max_workers: int = 4):
    """主函数"""
    setup_logging()

    fetcher = SamTurnerFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=0,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Sam Turner 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    samturner_fetch_info(max_workers=4)
