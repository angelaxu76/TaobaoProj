# -*- coding: utf-8 -*-
"""
Sam Turner (sam-turner.co.uk) | Barbour 商品链接抓取脚本

站点特点 (Shopify):
- collection 页面自带标准 JSON 接口, 直接分页拉取, 无需渲染/解析 HTML:
    https://www.sam-turner.co.uk/collections/barbour/products.json?limit=250&page=N
- 每个 product 对象带 "handle", 拼成 /products/<handle> 即详情页链接
- vendor 字段实测全部为 "Barbour", 可用于二次校验
- 注意: 该站不少商品把同一款式的多个颜色放在同一个商品页里 (variants 里混着
  不同 Colour), 一个链接对应的是"一个款式", 不是"一个颜色", 详情抓取阶段
  (samturner_fetch_info.py) 会按颜色拆分成多个 Product Code 分别写 TXT

使用方式:
    python -m brands.barbour.supplier.samturner_get_links
"""

from __future__ import annotations

import time

import requests

from config import BARBOUR

BASE_URL = "https://www.sam-turner.co.uk"
COLLECTION_HANDLE = "barbour"
PAGE_LIMIT = 250

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["samturner"]
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


def samturner_get_links():
    print(f"🚀 开始抓取 Sam Turner | Barbour 商品链接 (collection={COLLECTION_HANDLE!r})")

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
    samturner_get_links()
