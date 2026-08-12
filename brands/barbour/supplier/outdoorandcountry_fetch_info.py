# -*- coding: utf-8 -*-
"""
Outdoor & Country 采集器 - 重构版 (使用 BaseFetcher)

基于 outdoorandcountry_fetch_info_v2.py 重构
特点:
- span.price-sales 价格
- button.size-variant 尺码
- MPN 字段获取编码
- 需要 parse_offer_info 辅助模块

对比:
- 旧版 (outdoorandcountry_fetch_info_v2.py): 442 行
- 新版 (本文件): ~150 行
- 代码减少: 66%

使用方式:
    python -m brands.barbour.supplier.outdoorandcountry_fetch_info_v3
"""

from __future__ import annotations

import atexit
import re
import threading
from pathlib import Path
from typing import Dict, Any
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

# 导入基类和工具
from brands.barbour.core.base_fetcher import BaseFetcher, setup_logging

# ── undetected_chromedriver 驱动池（按线程 id 隔离）──────────────────
# OutdoorAndCountry 被 Cloudflare 保护，必须用 uc 绕过；
# 标准 headless Selenium 会触发 Cloudflare managed challenge。
_uc_drivers: dict = {}
_uc_lock = threading.Lock()


def _cleanup_uc_drivers():
    with _uc_lock:
        items = list(_uc_drivers.items())
        _uc_drivers.clear()
    for _, d in items:
        try:
            d.quit()
        except Exception:
            pass


atexit.register(_cleanup_uc_drivers)

# 导入站点特定的解析模块
from brands.barbour.supplier.outdoorandcountry_parse_offer_info import parse_offer_info

# 配置
from config import BARBOUR, SETTINGS

SITE_NAME = "outdoorandcountry"
LINKS_FILE = BARBOUR["LINKS_FILES"][SITE_NAME]
OUTPUT_DIR = BARBOUR["TXT_DIRS"][SITE_NAME]
DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)

# Outdoor 强风控站点：有效并发上限（与 v2 一致）
EFFECTIVE_MAX_WORKERS = 2


# ================== 采集器实现 ==================

class OutdoorAndCountryFetcher(BaseFetcher):
    """
    Outdoor & Country 采集器

    特点:
    - 使用 parse_offer_info 解析 offers (尺码/库存/价格)
    - 从 JSON-LD 提取 Product Code
    - MPN 字段优先
    """


    def get_driver(self):
        """
        使用 undetected_chromedriver（非无头）代替标准 Selenium。
        OutdoorAndCountry 受 Cloudflare 保护；headless Selenium 会触发
        managed challenge，uc 在有窗口模式下可让 challenge JS 自动通过。
        """
        key = f"oc_uc_{threading.get_ident()}"
        with _uc_lock:
            if key not in _uc_drivers:
                from common.browser.driver_auto import build_uc_driver
                driver = build_uc_driver(
                    headless=False,
                    extra_options=[
                        "--window-size=1920,1080",
                        "--blink-settings=imagesEnabled=false",
                        "--disable-notifications",
                    ],
                    verbose=True,
                )
                _uc_drivers[key] = driver
                self.logger.info(f"🚗 [uc] undetected_chromedriver 已启动 (key={key})")
            return _uc_drivers[key]

    def quit_driver(self):
        key = f"oc_uc_{threading.get_ident()}"
        with _uc_lock:
            driver = _uc_drivers.pop(key, None)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    def _fetch_html(self, url: str) -> str:
        """
        导航到页面，等待 Cloudflare challenge 自动通过后 var stockInfo 出现。
        超时上限 30s：challenge 解决约需 5-10s，之后页面正常渲染。
        """
        driver = self.get_driver()
        driver.get(url)
        try:
            WebDriverWait(driver, 30).until(
                lambda d: "var stockInfo" in d.page_source
            )
        except TimeoutException:
            self.logger.warning(f"等待 stockInfo 超时 (30s)，继续使用当前 page_source: {url}")
        return driver.page_source

    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析 Outdoor & Country 商品详情页

        页面特点:
        - parse_offer_info 提供基础信息
        - JSON-LD 的 MPN 字段包含编码
        - 需要从 URL 提取颜色
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. 使用站点特定解析器获取基础信息
        info = parse_offer_info(html, url, site_name=SITE_NAME) or {}

        # 2. 提取名称
        name = info.get("Product Name", "No Data")

        # 3. 提取颜色 (从 URL 或解析结果)
        color = info.get("Product Color") or self._normalize_color_from_url(url)

        # 4. 提取描述
        description = self._extract_description(html)

        # 5. 提取特征
        features = self._extract_features(html)

        # 6. 提取 Product Code (从 JSON-LD MPN)
        product_code = info.get("Product Color Code") or self._extract_color_code_from_jsonld(html)

        # 7. 推断性别
        gender = self.infer_gender(
            text=name,
            url=url,
            product_code=product_code,
            output_format="zh",  # 中文输出
        )

        # 8. 格式化尺码 (从 offers)
        offers = info.get("Offers", [])
        product_size_detail = self._build_sizes_from_offers(offers, gender)

        # 9. 提取价格
        original_price = info.get("original_price_gbp", "No Data")
        discount_price = info.get("discount_price_gbp", "No Data")

        # 10. 提取尺码表 (Measurements，部分商品才有)
        measurements = self._extract_measurements(html)

        # 11. 返回标准化字典
        return {
            "Product Code": product_code or "No Data",
            "Product Name": self.clean_text(name, maxlen=200),
            "Product Color": self.clean_text(color, maxlen=100),
            "Product Gender": gender,
            "Product Description": self.clean_description(description),
            "Product Price": original_price,        # txt_writer / DB 导入使用此 key
            "Adjusted Price": discount_price,        # txt_writer / DB 导入使用此 key
            "Original Price (GBP)": original_price,  # BaseFetcher._validate_info 要求
            "Discount Price (GBP)": discount_price,  # BaseFetcher._validate_info 要求
            "Product Size": self.size_from_detail(product_size_detail),
            "Product Size Detail": product_size_detail,
            "Feature": features,
            "Measurements": measurements,
        }

    def _normalize_color_from_url(self, url: str) -> str:
        """从 URL 参数提取颜色 (?c=xxx)"""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
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

    def _extract_description(self, html: str) -> str:
        """提取商品描述"""
        soup = BeautifulSoup(html, "html.parser")

        # 优先 og:description
        tag = soup.find("meta", attrs={"property": "og:description"})
        if tag and tag.get("content"):
            desc = tag["content"]
            desc = desc.replace("<br>", "").replace("<br/>", "").replace("<br />", "")
            return desc.strip()

        # 兜底: product_tabs
        tab = soup.select_one(".product_tabs .tab_content[data-id='0'] div")
        if tab:
            return tab.get_text(" ", strip=True)

        return "No Data"

    def _extract_features(self, html: str) -> str:
        """提取产品特征列表"""
        soup = BeautifulSoup(html, "html.parser")

        h3 = soup.find("h3", attrs={"title": "Features"})
        if h3:
            ul = h3.find_next("ul")
            if ul:
                items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                return "; ".join(items)

        return "No Data"

    def _extract_measurements(self, html: str) -> list:
        """
        提取 Measurements 尺码表 (仅部分商品提供，如 corbridge waxed jacket)

        页面结构:
            <table class="MeasureGrid" id="MeasurementGrid">
                <tbody>
                    <tr><th>Size</th><th>Back Length (CM)</th>...</tr>
                    <tr><td>S</td><td>77</td>...</tr>
                    ...
                </tbody>
            </table>

        返回行列表 [[表头...], [数据行...], ...]，无表格则返回 []。
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="MeasurementGrid") or soup.find("table", class_="MeasureGrid")
        if not table:
            return []

        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)

        return rows

    def _extract_color_code_from_jsonld(self, html: str) -> str:
        """从 JSON-LD 的 MPN 字段提取 Barbour Product Code"""
        import json
        soup = BeautifulSoup(html, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = (script.string or "").strip()
                if not raw:
                    continue

                j = json.loads(raw)
                candidates = j if isinstance(j, list) else [j]

                for obj in candidates:
                    if not isinstance(obj, dict) or obj.get("@type") != "Product":
                        continue

                    offers = obj.get("offers")
                    if not offers:
                        continue

                    offers_list = offers if isinstance(offers, list) else [offers]

                    for off in offers_list:
                        mpn = (off or {}).get("mpn")
                        if not isinstance(mpn, str):
                            continue

                        # MPN 格式: "MCA0538NY71_34"
                        mpn = mpn.split("_")[0].strip()

                        # 提取前 11 位作为 Product Code
                        if len(mpn) >= 11:
                            maybe_code = mpn[:11]
                            if re.match(r"^[A-Z]{3}\d{4}[A-Z]{2}\d{2}$", maybe_code):
                                return maybe_code

            except Exception:
                continue

        return ""

    def _build_sizes_from_offers(self, offers, gender: str) -> str:
        """从 offers 构建 Product Size Detail（经由 size_normalizer 标准化）"""
        if not offers:
            return "No Data"

        size_detail: Dict[str, Any] = {}
        for size, price, stock_text, can_order in offers:
            size = (size or "").strip()
            if not size:
                continue

            stock = 0
            if (stock_text or "").strip() in ("有货", "In Stock", "available"):
                stock = DEFAULT_STOCK_COUNT
            if can_order and stock == 0:
                stock = DEFAULT_STOCK_COUNT

            cs = self._clean_size(size)
            if not cs:
                continue

            if cs not in size_detail or stock > size_detail[cs]["stock_count"]:
                size_detail[cs] = {"stock_count": stock, "ean": "0000000000000"}

        if not size_detail:
            return "No Data"

        _, product_size_detail = self.build_size_lines(size_detail, gender)
        return product_size_detail

    def _write_output(self, info: Dict[str, Any]) -> None:
        """写入商品 TXT，并在存在 Measurements 时额外写入 <编码>_size.html 尺码表页面"""
        super()._write_output(info)

        rows = info.get("Measurements")
        if not rows:
            return

        from brands.barbour.core.text_utils import safe_filename

        code = info.get("Product Code", "").strip()
        if not code or code in ["Unknown", "No Data", "N/A", ""]:
            url = info.get("Source URL", "")
            code = f"NoCode_{abs(hash(url)) & 0xFFFFFFFF:08x}"

        style_name = self._derive_style_name(info.get("Product Name", ""))
        html_page = self._build_measurement_html(style_name, rows)

        safe_code = safe_filename(code)
        size_dir = self.output_dir.parent / "size"
        size_dir.mkdir(parents=True, exist_ok=True)
        size_path = size_dir / f"{safe_code}_size.html"

        try:
            size_path.write_text(html_page, encoding="utf-8")
            self.logger.debug(f"写入尺码表页面: {size_path}")
        except Exception as e:
            self.logger.error(f"尺码表页面写入失败 {size_path}: {e}")

    # 表头英文关键词 → 中文（按顺序匹配，先匹配先用）
    _MEASUREMENT_HEADER_MAP = [
        (r"\bsize\b", "尺码"),
        (r"\bsleeve\b", "袖长"),
        (r"\bchest\b", "胸围"),
        (r"\bshoulder\b", "肩宽"),
        (r"\bwaist\b", "腰围"),
        (r"\bhip\b", "臀围"),
        (r"\bcollar\b", "领围"),
        (r"\bneck\b", "领围"),
        (r"\bback length\b", "衣长"),
        (r"\bfront length\b", "衣长"),
        (r"\blength\b", "衣长"),  # 通用兜底，需放最后
    ]

    def _translate_measurement_header(self, header: str) -> str:
        """将英文表头翻译为中文，保留括号内单位；未识别的表头原样返回"""
        h = (header or "").strip()
        unit_match = re.search(r"\(([^)]+)\)", h)
        unit = f"({unit_match.group(1).upper()})" if unit_match else ""
        base = re.sub(r"\([^)]*\)", "", h).strip().lower()

        for pattern, zh in self._MEASUREMENT_HEADER_MAP:
            if re.search(pattern, base):
                return f"{zh}{unit}"

        return header

    def _derive_style_name(self, product_name: str) -> str:
        """从商品名去除性别前缀和品牌名，得到款式名称，如 'Corbridge Waxed Jacket'"""
        name = (product_name or "").strip()
        name = re.sub(r"^(men'?s|women'?s|ladies'?|kids'?|boys'?|girls'?)\s+", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\bbarbour\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name).strip()
        return name or product_name or "商品"

    def _build_measurement_html(self, style_name: str, rows: list) -> str:
        """按 test/barbour男polo.html 风格生成实测尺码表页面"""
        header, *data_rows = rows
        header_zh = [self._translate_measurement_header(h) for h in header]

        title = f"BARBOUR {style_name} 实测尺码表"

        header_html = "".join(f"<th>{h}</th>" for h in header_zh)
        body_html = "\n".join(
            "    <tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            for row in data_rows
        )

        return f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

<style>
    body {{
        background-color: #f3f4f2;
        font-family: Arial, sans-serif;
        text-align: center;
        margin: 0;
        padding: 0;
    }}

    .container {{
        max-width: 800px;
        margin: 20px auto;
        background-color: #ffffff;
        padding: 30px;
        border-radius: 14px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
        border: 1.5px solid #e2e2e2;
        text-align: left;
    }}

    h2 {{
        color: #ffffff;
        background-color: #7a0f14;
        text-align: center;
        font-size: 48px;
        padding: 20px;
        border-radius: 12px 12px 0 0;
        letter-spacing: 1px;
    }}

    h3 {{
        font-size: 33px;
        font-weight: bold;
        border-left: 6px solid #7a0f14;
        padding-left: 15px;
        margin-top: 28px;
        color: #2c2c2c;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 14px;
        border: 1.5px solid #e5e5e5;
        border-radius: 10px;
        overflow: hidden;
    }}

    th {{
        background-color: #3a3a3a;
        color: #ffffff;
        border: 1px solid #d9d9d9;
        padding: 15px;
        text-align: center;
        font-size: 27px;
        font-weight: bold;
    }}

    td {{
        border: 1px solid #e6e6e6;
        padding: 15px;
        text-align: center;
        font-size: 27px;
        color: #333333;
    }}

    tr:nth-child(even) td {{
        background-color: #f7f7f7;
    }}

    tr:nth-child(odd) td {{
        background-color: #ffffff;
    }}

    li {{
        color: #3a3a3a;
        line-height: 1.7;
    }}

    strong {{
        font-weight: bold;
        color: #8B0000;
    }}
</style>

</head>
<body>

<div class="container">

    <h2 style="font-size:50px;">{title}</h2>

    <table>
    <tr>{header_html}</tr>
{body_html}
    </table>

    <h3 style="font-size:36px;">选码建议</h3>

    <ul>
        <li style="font-size:30px;">衣服实测胸围比人体净胸围大 <strong>10-15cm</strong>，上身效果最佳；</li>
        <li style="font-size:30px;">建议先测量一件自己已穿着合适、版型相近的衣服的胸围，与上表比对后再选择尺码。</li>
    </ul>

</div>

</body>
</html>
"""

    def _clean_size(self, raw: str) -> str:
        """清理尺码"""
        from common.product.size_utils import clean_size_for_barbour

        raw = (raw or "").strip()
        if not raw:
            return ""

        s = clean_size_for_barbour(raw) or raw
        return s.strip()


# ================== 主入口 ==================

def outdoorandcountry_fetch_info(
    max_workers: int = 2,
    headless: bool = True,
):
    """
    主函数 - 兼容旧版接口

    Args:
        max_workers: 并发线程数 (建议 2, Outdoor 强风控)
        headless: 是否无头模式
    """
    setup_logging()

    effective = int(max_workers)
    print(f"🔄 Outdoor&Country v3: 请求并发 {max_workers}, 有效并发 {effective}", flush=True)

    fetcher = OutdoorAndCountryFetcher(
        site_name=SITE_NAME,
        links_file=LINKS_FILE,
        output_dir=OUTPUT_DIR,
        max_workers=effective,
        max_retries=3,
        wait_seconds=2.0,
        headless=headless,
    )

    success, fail = fetcher.run_batch()
    print(f"\n✅ Outdoor & Country 抓取完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    outdoorandcountry_fetch_info(max_workers=2, headless=True)
