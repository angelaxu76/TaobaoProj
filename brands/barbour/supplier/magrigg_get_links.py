# -*- coding: utf-8 -*-
"""
Magrigg (Griggs / magrigg.co.uk) | Barbour 商品链接抓取脚本

站点特点:
- 搜索页 https://www.magrigg.co.uk/search/?q=barbour 由 Klevu 搜索插件
  异步渲染, 静态 HTML 里没有商品链接, 无法直接 BeautifulSoup 解析
- 改为直接调用 Klevu 前端使用的搜索接口 (JSON POST), 用 limit/offset 分页
  拉取全部结果, 每条记录自带 "url" 字段即商品详情页链接

使用方式:
    python -m brands.barbour.supplier.magrigg_get_links
"""

from __future__ import annotations

import time

import requests

from config import BARBOUR

KLEVU_SEARCH_URL = "https://eucs24v2.ksearchnet.com/cs/v2/search"
KLEVU_API_KEY = "klevu-161166795463513123"
SEARCH_TERM = "barbour"
PAGE_LIMIT = 100

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["magrigg"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _fetch_page(session: requests.Session, offset: int) -> dict:
    """请求一页 Klevu 搜索结果, 返回该 recordQuery 的结果字典"""
    payload = {
        "context": {"apiKeys": [KLEVU_API_KEY]},
        "recordQueries": [
            {
                "id": "search",
                "typeOfRequest": "SEARCH",
                "settings": {
                    "typeOfRecords": ["KLEVU_PRODUCT"],
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                    "query": {"term": SEARCH_TERM},
                },
            }
        ],
    }
    resp = session.post(KLEVU_SEARCH_URL, json=payload, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()["queryResults"][0]


def magrigg_get_links():
    print(f"🚀 开始抓取 Magrigg | Barbour 商品链接 (Klevu 搜索接口, term={SEARCH_TERM!r})")

    session = requests.Session()
    all_links: set[str] = set()
    offset = 0
    total = None

    while True:
        result = _fetch_page(session, offset)
        meta = result.get("meta", {})
        total = meta.get("totalResultsFound", 0)
        records = result.get("records", [])

        if not records:
            print(f"⚠️ offset={offset} 未返回记录, 结束翻页")
            break

        before_count = len(all_links)
        for rec in records:
            url = (rec.get("url") or "").strip()
            if url:
                all_links.add(url)
        after_count = len(all_links)

        print(
            f"✅ offset={offset}: 返回 {len(records)} 条, "
            f"新增 {after_count - before_count} 个链接, "
            f"累计 {after_count}/{total}"
        )

        offset += PAGE_LIMIT
        if offset >= total:
            break

        time.sleep(0.5)  # 友好一点，别刷太猛

    sorted_links = sorted(all_links)
    OUTPUT_PATH.write_text("\n".join(sorted_links), encoding="utf-8")

    print("\n🎯 抓取完成")
    print(f"📦 共提取 {len(sorted_links)} 条商品链接 (接口报告总数 {total})")
    print(f"💾 已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    magrigg_get_links()
