# -*- coding: utf-8 -*-
"""
William Powell (williampowell.com) | Barbour 商品链接抓取脚本

站点特点 (Shopify):
- collection 页面自带标准 JSON 接口, 直接分页拉取, 无需渲染/解析 HTML:
    https://williampowell.com/collections/barbour/products.json?limit=250&page=N
- 每个 product 对象带 "handle", 拼成 /products/<handle> 即详情页链接
- vendor 字段实测全部为 "Barbour", 可用于二次校验

使用方式:
    python -m brands.barbour.supplier.williampowell_get_links
"""

from __future__ import annotations

import time

import requests

from config import BARBOUR

BASE_URL = "https://williampowell.com"
COLLECTION_HANDLE = "barbour"
PAGE_LIMIT = 250

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["williampowell"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _fetch_page(session: requests.Session, page: int) -> list[dict]:
    url = f"{BASE_URL}/collections/{COLLECTION_HANDLE}/products.json"
    resp = session.get(url, params={"limit": PAGE_LIMIT, "page": page}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def williampowell_get_links():
    print(f"🚀 开始抓取 William Powell | Barbour 商品链接 (collection={COLLECTION_HANDLE!r})")

    session = requests.Session()
    all_links: set[str] = set()
    page = 1

    while True:
        products = _fetch_page(session, page)
        if not products:
            print(f"⚠️ page={page} 未返回商品, 结束翻页")
            break

        before_count = len(all_links)
        skipped_non_barbour = 0
        for p in products:
            if (p.get("vendor") or "").strip().lower() != "barbour":
                skipped_non_barbour += 1
                continue
            handle = (p.get("handle") or "").strip()
            if handle:
                all_links.add(f"{BASE_URL}/products/{handle}")
        after_count = len(all_links)

        print(
            f"✅ page={page}: 返回 {len(products)} 条, "
            f"新增 {after_count - before_count} 个链接"
            + (f" (跳过非 Barbour {skipped_non_barbour} 条)" if skipped_non_barbour else "")
            + f", 累计 {after_count}"
        )

        page += 1
        time.sleep(0.5)  # 友好一点，别刷太猛

    sorted_links = sorted(all_links)
    OUTPUT_PATH.write_text("\n".join(sorted_links), encoding="utf-8")

    print("\n🎯 抓取完成")
    print(f"📦 共提取 {len(sorted_links)} 条商品链接")
    print(f"💾 已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    williampowell_get_links()
