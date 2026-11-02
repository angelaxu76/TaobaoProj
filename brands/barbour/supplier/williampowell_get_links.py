# -*- coding: utf-8 -*-
"""
William Powell (williampowell.com) | Barbour 商品链接抓取脚本

站点特点 (Shopify):
- collection 页面自带标准 JSON 接口, 直接分页拉取, 无需解析 HTML:
    https://williampowell.com/collections/barbour/products.json?limit=250&page=N
- 每个 product 对象带 "handle", 拼成 /products/<handle> 即详情页链接
- vendor 字段实测全部为 "Barbour", 可用于二次校验
- 站点对 requests / curl 这类非浏览器请求整 IP 返回 429 (HTML 页面也一样),
  真实 Chrome 不受影响: 先用 Selenium 打开 collection 页面, 再在页面里
  fetch() 上面的 JSON 接口翻页

使用方式:
    python -m brands.barbour.supplier.williampowell_get_links
"""

from __future__ import annotations

import json
import time

from common.browser.selenium_utils import get_driver, quit_driver
from config import BARBOUR

BASE_URL = "https://williampowell.com"
COLLECTION_HANDLE = "barbour"
PAGE_LIMIT = 250

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["williampowell"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

DRIVER_NAME = "williampowell_collection"
PAGE_INTERVAL = 3.0   # 翻页间隔
MAX_RETRIES = 5
MAX_PAGES = 50        # 防止接口异常时无限翻页

_FETCH_JS = """
const done = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: "include"})
  .then(async r => done({status: r.status, retryAfter: r.headers.get("Retry-After"), body: await r.text()}))
  .catch(e => done({status: -1, retryAfter: null, body: String(e)}));
"""


def _fetch_page(driver, page: int) -> list[dict]:
    # 第 1 页不带 page 参数: 带 page=1 的请求更容易被限流
    query = f"limit={PAGE_LIMIT}" if page == 1 else f"limit={PAGE_LIMIT}&page={page}"
    url = f"/collections/{COLLECTION_HANDLE}/products.json?{query}"
    for attempt in range(1, MAX_RETRIES + 1):
        res = driver.execute_async_script(_FETCH_JS, url)
        status = res.get("status")
        if status == 200:
            return json.loads(res["body"]).get("products", [])
        if attempt == MAX_RETRIES:
            break
        try:
            wait = float(res.get("retryAfter") or 0)
        except ValueError:
            wait = 0
        wait = max(wait, 30.0 * 2 ** (attempt - 1))   # 指数退避 30/60/120/240/480s
        print(f"⏳ page={page} HTTP {status}, 等待 {wait:.0f}s 后重试 ({attempt}/{MAX_RETRIES})")
        time.sleep(wait)
    raise RuntimeError(f"William Powell products.json page={page} 失败: HTTP {status} {str(res.get('body'))[:100]}")


def fetch_all_collection_products() -> list[dict]:
    """用浏览器拉取整个 collection 的 products.json, 返回全部 product 对象 (get_links / fetch_info 共用)"""
    driver = get_driver(DRIVER_NAME, headless=True)
    try:
        driver.set_script_timeout(60)
        driver.get(f"{BASE_URL}/collections/{COLLECTION_HANDLE}")
        time.sleep(3)

        products: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            batch = _fetch_page(driver, page)
            if not batch:
                print(f"⚠️ page={page} 未返回商品, 结束翻页")
                break
            products.extend(batch)
            print(f"✅ page={page}: 返回 {len(batch)} 条, 累计 {len(products)}")
            time.sleep(PAGE_INTERVAL)
        return products
    finally:
        quit_driver(DRIVER_NAME)


def williampowell_get_links():
    print(f"🚀 开始抓取 William Powell | Barbour 商品链接 (collection={COLLECTION_HANDLE!r})")

    all_links: set[str] = set()
    skipped_non_barbour = 0
    for p in fetch_all_collection_products():
        if (p.get("vendor") or "").strip().lower() != "barbour":
            skipped_non_barbour += 1
            continue
        handle = (p.get("handle") or "").strip()
        if handle:
            all_links.add(f"{BASE_URL}/products/{handle}")

    if not all_links:
        raise RuntimeError("William Powell 未获取到任何商品链接")

    sorted_links = sorted(all_links)
    OUTPUT_PATH.write_text("\n".join(sorted_links), encoding="utf-8")

    print("\n🎯 抓取完成")
    if skipped_non_barbour:
        print(f"⏭  跳过非 Barbour {skipped_non_barbour} 条")
    print(f"📦 共提取 {len(sorted_links)} 条商品链接")
    print(f"💾 已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    williampowell_get_links()
