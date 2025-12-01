# brands/barbour/supplier/cho_get_links.py
# -*- coding: utf-8 -*-

"""
CHO | Barbour 商品链接抓取脚本 (V2 稳定版)

特性：
- 支持多个类目：
    https://www.cho.co.uk/collections/barbour
    https://www.cho.co.uk/collections/barbour-international
- ?page=1,2,3... 翻页
- 从列表页提取所有 /products/ 商品链接
- 通过“是否出现新链接”判断是否已经到最后一页
- 输出到 config.BARBOUR["LINKS_FILES"]["cho"]
"""

import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import BARBOUR
from common_taobao.core.selenium_utils import get_driver, quit_driver

# ========= 类目配置：在这里增删类目链接 =========
CATEGORY_URLS = [
    "https://www.cho.co.uk/collections/barbour",
    "https://www.cho.co.uk/collections/barbour-international",
]

# 输出路径：使用 config 中定义好的 cho 链接文件
OUTPUT_PATH: Path = BARBOUR["LINKS_FILES"]["cho"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_cho_driver():
    """
    统一从 common_taobao.selenium_utils 获取 driver，
    名字用 'cho'，方便之后关闭或复用。
    """
    return get_driver(
        name="cho",
        headless=False,          # 需要无头可以改成 True
        window_size="1200,2000",
    )


def extract_links_from_html(html: str) -> set[str]:
    """
    从 CHO 列表页 HTML 中提取商品详情链接。

    规则：
    - 任意 <a> 标签，只要 href 中包含 '/products/' 就认为是商品链接
    - 自动补全相对路径
    """
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if "/products/" not in href.lower():
            continue

        if href.startswith("http"):
            full = href
        elif href.startswith("/"):
            full = "https://www.cho.co.uk" + href
        else:
            # 极少数情况出现相对链接
            full = "https://www.cho.co.uk/" + href.lstrip("/")

        links.add(full)

    return links


def build_page_url(base_url: str, page: int) -> str:
    """
    根据 base_url 构造分页 URL：
    - 已包含 ? 时用 &page=
    - 否则用 ?page=
    """
    if "?" in base_url:
        return f"{base_url}&page={page}"
    else:
        return f"{base_url}?page={page}"


def cho_get_links():
    print("🚀 开始抓取 CHO | Barbour 商品链接（多类目）")

    driver = get_cho_driver()
    all_links: set[str] = set()

    try:
        for idx, base_url in enumerate(CATEGORY_URLS, start=1):
            print("\n============================")
            print(f"📂 类目 {idx}/{len(CATEGORY_URLS)}: {base_url}")

            page = 1
            while True:
                page_url = build_page_url(base_url, page)
                print(f"🌐 抓取第 {page} 页: {page_url}")
                driver.get(page_url)

                # 等待页面出现至少一个商品链接（/products/）
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "a[href*='/products/']")
                        )
                    )
                except Exception:
                    print(f"⚠️ 第 {page} 页加载失败或无有效商品链接，结束该类目")
                    break

                html = driver.page_source
                page_links = extract_links_from_html(html)

                if not page_links:
                    # 理论上不会出现，因为我们已经等到 a[href*='/products/']
                    print(f"⚠️ 第 {page} 页未提取到任何商品链接，结束该类目")
                    break

                # 统计“新出现”的链接数量
                before_count = len(all_links)
                new_links = [u for u in page_links if u not in all_links]
                all_links.update(new_links)
                after_count = len(all_links)

                print(
                    f"✅ 第 {page} 页提取 {len(page_links)} 个链接，"
                    f"其中新链接 {len(new_links)} 个，"
                    f"累计总数 {after_count}"
                )

                # 💡 关键终止条件：
                # 如果这一页没有产生任何“新链接”，说明已经进入广告循环页 → 停止翻页
                if after_count == before_count:
                    print(
                        f"⛔ 本页未产生新的商品链接，推断已经到最后一页，"
                        f"结束该类目翻页（page={page}）。"
                    )
                    break

                page += 1
                time.sleep(1)  # 友好一点，别刷太猛

    finally:
        # 关闭 driver
        quit_driver("cho")

    # 写入文件（去重后的总集合）
    sorted_links = sorted(all_links)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sorted_links), encoding="utf-8")

    print("\n🎯 抓取完成")
    print(f"📦 共提取 {len(sorted_links)} 条商品链接（多类目去重后总数）")
    print(f"💾 已保存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    cho_get_links()
