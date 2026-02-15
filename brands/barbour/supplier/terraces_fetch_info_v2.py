# -*- coding: utf-8 -*-
"""
Terraces Menswear 采集器 - 重构版 (使用 BaseFetcher)

基于 terraces_fetch_info.py 重构
特点:
- 需要 UC 驱动 (undetected_chromedriver)
- meta[name="twitter:title"] 标题
- div.product-price 价格
- 数据库匹配 (sim_matcher)

对比:
- 旧版 (terraces_fetch_info.py): 667 行
- 新版 (本文件): ~250 行
- 代码减少: 62%

使用方式:
    python -m brands.barbour.supplier.terraces_fetch_info_v2
"""

from __future__ import annotations

import re
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# 导入统一匹配器
from brands.barbour.core.hybrid_barbour_matcher import resolve_product_code

# SQLAlchemy
from sqlalchemy import create_engine

# 配置
from config import BARBOUR, BRAND_CONFIG, SETTINGS

SITE_NAME = "terraces"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# 数据库配置
PRODUCTS_TABLE = BRAND_CONFIG.get("barbour", {}).get("PRODUCTS_TABLE", "barbour_products")
OFFERS_TABLE = BRAND_CONFIG.get("barbour", {}).get("OFFERS_TABLE")
PG = BRAND_CONFIG["barbour"]["PGSQL_CONFIG"]

# 尺码常量
WOMEN_ORDER = ["4", "6", "8", "10", "12", "14", "16", "18", "20"]
MEN_ALPHA_ORDER = ["2XS", "XS", "S", "M", "L", "XL", "2XL", "3XL"]
MEN_NUM_ORDER = [str(n) for n in range(30, 52, 2)]  # 30..50

ALPHA_MAP = {
    "XXXS": "2XS", "2XS": "2XS",
    "XXS": "XS", "XS": "XS",
    "S": "S", "SMALL": "S",
    "M": "M", "MEDIUM": "M",
    "L": "L", "LARGE": "L",
    "XL": "XL", "X-LARGE": "XL",
    "XXL": "2XL", "2XL": "2XL",
    "XXXL": "3XL", "3XL": "3XL",
}


# ================== 采集器实现 ==================

class TerracesFetcher(BaseFetcher):
    """
    Terraces Menswear 采集器

    特点:
    - 使用 selenium_utils 管理驱动（per-thread 复用）
    - hybrid_barbour_matcher 多级匹配
    - 断点续传（自动跳过已完成的 URL）
    """

    def __init__(self, *args, **kwargs):
        """初始化 + 数据库引擎 + 进度文件"""
        super().__init__(*args, **kwargs)

        # 创建数据库引擎
        engine_url = (
            f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
            f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
        )
        self._engine = create_engine(engine_url, pool_size=self.max_workers + 2)

        # 断点续传：进度文件
        self._progress_file = Path(self.output_dir) / ".done_urls.txt"
        self._done_urls = self._load_done_urls()
        self._progress_lock = threading.Lock()

    # ================== 断点续传 ==================

    def _load_done_urls(self) -> set:
        """加载已完成的 URL 集合"""
        if not self._progress_file.exists():
            return set()
        try:
            lines = self._progress_file.read_text(encoding="utf-8").splitlines()
            done = {line.strip() for line in lines if line.strip()}
            self.logger.info(f"📋 已完成 {len(done)} 个，自动跳过")
            return done
        except Exception:
            return set()

    def _mark_done(self, url: str) -> None:
        """记录已完成的 URL（线程安全、追加写入）"""
        with self._progress_lock:
            self._done_urls.add(url)
            try:
                with open(self._progress_file, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
            except Exception:
                pass

    def _load_urls(self) -> List[str]:
        """重写：加载链接并过滤掉已完成的"""
        all_urls = super()._load_urls()
        before = len(all_urls)
        urls = [u for u in all_urls if u not in self._done_urls]
        skipped = before - len(urls)
        if skipped > 0:
            self.logger.info(f"⏭️ 跳过已完成 {skipped} 个，剩余 {len(urls)} 个待抓取")
        return urls

    def fetch_one_product(self, url: str, idx: int, total: int):
        """重写：成功后记录进度"""
        result = super().fetch_one_product(url, idx, total)
        url_out, success = result
        if success:
            self._mark_done(url_out)
        return result

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析 Terraces 商品详情页

        页面特点:
        - 标题: "Name - Color" 格式
        - 价格: .product__price
        - 尺码: JSON 或 DOM
        - 需要数据库匹配获取 Product Code
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 提取标题和颜色
        h1 = soup.select_one("h1.primary-title a") or soup.select_one("h1.primary-title")
        raw_title = self._text(h1)

        # 从 span 提取颜色
        color_from_span = ""
        if h1:
            span = h1.find("span")
            if span:
                color_from_span = self._text(span)
                if color_from_span:
                    raw_title = re.sub(
                        rf"\s*\b{re.escape(color_from_span)}\b\s*$",
                        "",
                        raw_title,
                        flags=re.I
                    ).strip()

        # 从标题分割颜色
        name, color_from_title = self._split_title_color(raw_title)

        # 最终名称和颜色
        name = name or raw_title or "No Data"
        color = color_from_span or color_from_title

        # 兜底: og:title
        if name == "No Data":
            og = soup.find("meta", {"property": "og:title"})
            if og and og.get("content"):
                name = og["content"].strip()

        # 从 JSON-LD 兜底颜色
        if not color:
            jsonld = self._parse_json_ld(soup)
            if isinstance(jsonld, dict):
                color = (jsonld.get("color") or "").strip()

        # 清理名称中的重复颜色
        if color:
            name = re.sub(
                rf"(?:\s+\b{re.escape(color)}\b)+\s*$",
                "",
                name,
                flags=re.I
            ).strip()

        # 2. 提取价格
        product_price, adjusted_price = self._extract_prices(soup, html)

        # 3. 提取性别 (Terraces 全为男款)
        gender = "Men"

        # 4. 提取尺码
        sizes, size_detail = self._extract_sizes(soup, gender)

        # 5. 提取描述和特征
        description, features = self._extract_description_and_features(soup, html)

        # 6. hybrid_barbour_matcher 多级匹配 Product Code
        product_code = self._match_product_code(name, color, url)

        # 7. 返回标准化字典
        return {
            "Product Code": product_code or "No Data",
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Color": self.clean_text(color, maxlen=100) if color else "No Data",
            "Product Gender": gender,
            "Product Description": self.clean_description(description),
            "Original Price (GBP)": product_price,
            "Discount Price (GBP)": adjusted_price,
            "Product Size": ";".join(sizes) if sizes else "No Data",
            "Product Size Detail": size_detail,
            "Feature": features,
        }

    def _text(self, el) -> str:
        """从元素提取文本"""
        return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""

    def _split_title_color(self, title: str):
        """分割标题和颜色 (格式: "Name - Color")"""
        t = (title or "").strip()
        if not t:
            return "No Data", None

        parts = [p.strip() for p in re.split(r"\s*-\s*", t) if p.strip()]
        if len(parts) >= 2:
            raw_color = parts[-1]
            # 多词颜色仅取第一个主词
            color = re.split(r"[\/&]", re.sub(r"[^\w\s/&-]", "", raw_color))[0].strip()
            color = color.title() if color else None
            clean_title = " - ".join(parts[:-1])
            return (clean_title or t, color or None)

        return t, None

    def _parse_json_ld(self, soup: BeautifulSoup) -> dict:
        """解析 JSON-LD"""
        for tag in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                obj = json.loads(tag.string or tag.get_text() or "{}")
                cand = obj[0] if isinstance(obj, list) and obj else obj
                if isinstance(cand, dict) and ("name" in cand or "offers" in cand or "color" in cand):
                    return cand
            except Exception:
                continue
        return {}

    def _extract_prices(self, soup: BeautifulSoup, html: str):
        """提取价格"""
        price_wrap = soup.select_one(".product__short-description .product__price") or soup.select_one(".product__price")

        adjusted_price = product_price = "No Data"

        if price_wrap:
            curr = price_wrap.select_one(".price:not(.price--compare)")
            comp = price_wrap.select_one(".price--compare")

            if curr:
                adjusted_price = self._price_to_num(self._text(curr))
            if comp:
                product_price = self._price_to_num(self._text(comp))

        # 兜底: JSON-LD
        if (adjusted_price == "No Data" or product_price == "No Data"):
            jsonld = self._parse_json_ld(soup)
            if isinstance(jsonld, dict):
                offers = jsonld.get("offers")
                if isinstance(offers, dict) and offers.get("price"):
                    adjusted_price = self._price_to_num(str(offers.get("price")))
                    if product_price == "No Data":
                        product_price = adjusted_price

        return product_price, adjusted_price

    def _price_to_num(self, s: str) -> str:
        """从文本提取价格数字"""
        s = (s or "").replace(",", "").strip()
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        return m.group(1) if m else "No Data"

    def _extract_sizes(self, soup: BeautifulSoup, gender: str):
        """提取尺码"""
        SIZE_PAT = re.compile(
            r"\b(One Size|OS|XXS|XS|S|M|L|XL|XXL|3XL|4XL|5|6|7|8|9|10|11|12|13|28|30|32|34|36|38|40|42|44|46|48|50)\b",
            re.I
        )

        sizes = []
        avail = {}  # 1=有货, 0=无货

        # 1) product JSON (优先)
        for tag in soup.find_all("script", {"type": "application/json"}):
            raw = (tag.string or tag.get_text() or "").strip()
            if not raw or "variants" not in raw:
                continue

            try:
                data = json.loads(raw)
            except Exception:
                continue

            variants = data.get("variants")
            if isinstance(variants, list) and variants:
                size_idx = None
                options = data.get("options")
                if isinstance(options, list):
                    for i, name in enumerate(options, 1):
                        if str(name).strip().lower() in ("size", "sizes"):
                            size_idx = i
                            break

                for v in variants:
                    is_avail = 1 if (v.get("available") or v.get("is_available") or v.get("in_stock")) else 0
                    sz = None

                    for key in filter(None, [f"option{size_idx}" if size_idx else None, "option1", "option2", "option3", "title"]):
                        val = v.get(key)
                        if val:
                            m = SIZE_PAT.search(str(val))
                            if m:
                                sz = m.group(0).strip()
                                break

                    if sz:
                        if sz not in sizes:
                            sizes.append(sz)
                        if avail.get(sz, -1) != 1:
                            avail[sz] = 1 if is_avail else 0

                if sizes:
                    break

        # 2) DOM 兜底
        if not sizes:
            for lab in soup.select("label.size-wrap"):
                btn = lab.find("button", class_="size-box")
                if not btn:
                    continue

                sz = (btn.get_text(" ", strip=True) or "").strip()
                if not sz or not SIZE_PAT.search(sz):
                    continue

                disabled = False
                inp = lab.find("input")
                if inp and (inp.has_attr("disabled") or str(inp.get("aria-disabled", "")).lower() == "true"):
                    disabled = True

                cls = " ".join(lab.get("class", [])).lower()
                if "disabled" in cls or "sold" in cls:
                    disabled = True

                if sz not in sizes:
                    sizes.append(sz)

                if avail.get(sz, -1) != 1:
                    avail[sz] = 0 if disabled else 1

        # 3) 标准化尺码
        present_norm = set()
        for s in sizes:
            cs = self._canon_token(s)
            if cs:
                present_norm.add(cs)

        full_order = self._choose_full_order_for_gender(gender, present_norm)

        # 格式化
        EAN = "0000000000000"
        if not sizes:
            detail = ";".join(f"{s}:0:{EAN}" for s in full_order)
            return [], detail

        detail = ";".join(
            f"{s}:{DEFAULT_STOCK_COUNT if avail.get(s, 0) == 1 else 0}:{EAN}"
            for s in full_order
        )
        return sizes, detail

    def _canon_token(self, tok: str) -> Optional[str]:
        """标准化尺码"""
        t = (tok or "").strip().upper().replace("UK ", "")

        # 字母系
        if t in ALPHA_MAP:
            return ALPHA_MAP[t]

        # 数字系: 30..50 的偶数
        if t.isdigit():
            n = int(t)
            if 30 <= n <= 50 and n % 2 == 0:
                return str(n)

        return None

    def _choose_full_order_for_gender(self, gender: str, present: set):
        """选择完整尺码顺序"""
        g = (gender or "").lower()
        if "女" in g or "women" in g or "ladies" in g:
            return WOMEN_ORDER[:]

        has_num = any(k in MEN_NUM_ORDER for k in present)
        has_alpha = any(k in MEN_ALPHA_ORDER for k in present)

        if has_num and not has_alpha:
            return MEN_NUM_ORDER[:]
        if has_alpha and not has_num:
            return MEN_ALPHA_ORDER[:]
        if has_num or has_alpha:
            num_count = sum(1 for k in present if k in MEN_NUM_ORDER)
            alpha_count = sum(1 for k in present if k in MEN_ALPHA_ORDER)
            return MEN_NUM_ORDER[:] if num_count >= alpha_count else MEN_ALPHA_ORDER[:]

        return MEN_ALPHA_ORDER[:]

    def _extract_description_and_features(self, soup: BeautifulSoup, html: str):
        """提取描述和特征"""
        features = []

        # 特征: Details 模块
        for head in soup.select(".section.product__details h3"):
            if "details" in self._text(head).lower():
                ul = head.find_next("ul")
                if ul:
                    features = [self._text(li) for li in ul.find_all("li")]
                    break

        if not features:
            ul = soup.select_one(".section.product__details ul")
            if ul:
                features = [self._text(li) for li in ul.find_all("li")]

        # 描述
        description = features[0] if features else ""

        # 兜底: JSON-LD
        if not description:
            jsonld = self._parse_json_ld(soup)
            if isinstance(jsonld, dict) and jsonld.get("description"):
                description = (jsonld["description"] or "").strip()

        # 再兜底: meta description
        if not description:
            meta = soup.find("meta", {"name": "description"})
            if meta and meta.get("content"):
                description = meta["content"].strip()

        feature_join = "; ".join(features) if features else "No Data"
        return description or "No Data", feature_join

    def _match_product_code(self, name: str, color: str, url: str) -> Optional[str]:
        """使用 hybrid_barbour_matcher 多级匹配 Product Code"""
        try:
            with self._engine.begin() as conn:
                try:
                    raw_conn = conn.connection
                except Exception:
                    raw_conn = conn.connection.connection

                code, debug_trace = resolve_product_code(
                    raw_conn,
                    site_name=SITE_NAME,
                    url=url,
                    scraped_title=name or "",
                    scraped_color=color or "",
                    sku_guess=None,
                    products_table=PRODUCTS_TABLE,
                    offers_table=OFFERS_TABLE,
                    brand="barbour",
                )

            self.logger.debug(f"匹配: title={name}, color={color}, code={code}")
            return code if code and code != "No Data" else None

        except Exception as e:
            self.logger.error(f"数据库匹配失败: {e}")
            return None


# ================== 主入口 ==================

def terraces_fetch_info(
    max_workers: int = 8,
    headless: bool = True,
):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数
        headless: 是否无头模式
    """
    setup_logging()

    fetcher = TerracesFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=max_workers,
        max_retries=3,
        wait_seconds=2.0,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Terraces 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    terraces_fetch_info(max_workers=8, headless=True)
