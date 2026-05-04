# -*- coding: utf-8 -*-
"""
Marks & Spencer 女款针织商品链接抓取（参考 camper 版本的逻辑）

功能：
1）支持多个类目入口（例如：女款针织开衫 / 羊毛衫等），每个入口按页数递增抓取。
2）自动翻页：从第 1 页开始，只要还能抓到商品就继续；
   如果发现「当前页商品列表和上一页完全一样」（比如被重定向回首页），就停止该类目。
3）从商品卡片 <a class="product-card_cardWrapper__..."> 中提取链接，避免抓到颜色小圆点的链接。
4）所有链接去重、排序后写入 config 中的 LINKS_FILE。
"""

import time
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urldefrag

from config import BRAND_CONFIG
CFG = BRAND_CONFIG["marksandspencer"]
OUTPUT_FILE_JACKET: Path = CFG["LINKS_FILE_JACKET"]
# ----------------------------------------------------------------------
# 配置区
# ----------------------------------------------------------------------

# 站点前缀
DOMAIN = "https://www.marksandspencer.com"

# 从全局 config 中读取 Marks & Spencer 品牌配置
CFG = BRAND_CONFIG["marksandspencer"]
OUTPUT_FILE_LINGERIE: Path = CFG["LINKS_FILE_LINGERIE"]
OUTPUT_FILE_JACKET: Path = CFG["LINKS_FILE_JACKET"]

# 请求头（带个 User-Agent 稍微友好一点）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 每个类目最多允许连续多少页“未发现商品”就停（备用）
MAX_EMPTY_PAGES = 3

# 请求之间的休眠，避免压力太大
SLEEP_SECONDS = 1.0

# ----------------------------------------------------------------------
# M&S 女款针织类目入口
# 统一使用 {} 作为 page 占位符，和 camper 脚本保持一致
# ----------------------------------------------------------------------
BASE_URLS = [
    # ✅ 你提供的：女款 M&S 品牌开衫
    # "https://www.marksandspencer.com/l/women/knitwear/cardigans?filter=Brand%253DM%2526S&page={}",

    # TODO：后续可以加 jumpers / 所有针织等
    "https://www.marksandspencer.com/l/women/knitwear/jumpers?filter=Brand%253DM%2526S&page={}",
    # "https://www.marksandspencer.com/l/women/knitwear?filter=Brand%253DM%2526S&page={}",
]

# --------------------------
# 外套（jacket）类目
# --------------------------
BASE_URLS_JACKET = [
    "https://www.marksandspencer.com/l/women/knitwear/cardigans?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/coats-and-jackets?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/dresses?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/knitwear/jumpers?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/dresses?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/knitwear/jumpers?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/tops/shirts-and-blouses?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/skirts?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/women/tops/tshirts?filter=Brand%253DM%2526S&page={}",

    "https://www.marksandspencer.com/l/men/mens-coats-and-jackets?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-coats-and-jackets/fs5/gilet?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-hoodies-and-sweatshirts?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-knitwear?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-tops/mens-polo-shirts?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-shirts/casual-shirts?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-shirts/fs5/overshirts?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/men/mens-shirts?filter=Brand%253DM%2526S&page={}",
    # 你可以继续加入 jumper、coat 等
]

# --------------------------
# 内衣（lingerie）类目
# --------------------------
BASE_URLS_LINGERIE = [
    "https://www.marksandspencer.com/l/lingerie/bras?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/lingerie/knickers?filter=Brand%253DM%2526S&page={}",
    "https://www.marksandspencer.com/l/lingerie/nightwear?filter=Brand%253DM%2526S&page={}",
    # 例如 bra、knickers 之类
    # "https://www.marksandspencer.com/l/women/lingerie/bras?page={}",
]


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------

def fetch_page(url: str) -> str | None:
    """请求一个列表页，返回 HTML 文本，失败则返回 None。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] {url} 返回状态码 {resp.status_code}", file=sys.stderr)
            return None
        return resp.text
    except Exception as e:
        print(f"[ERROR] 请求失败: {url} -> {e}", file=sys.stderr)
        return None


def extract_product_links(html: str) -> list[str]:
    """
    从列表页 HTML 中提取商品链接。

    根据你提供的页面结构，每个商品卡片大致是：
        <a class="product-card_cardWrapper__GVSTY" href="https://www.marksandspencer.com/...">...</a>

    我们只抓 class 中包含 "product-card_cardWrapper" 的 <a>，
    可以避免抓到颜色小圆点（colour-swatch_element）之类的链接。
    """
    soup = BeautifulSoup(html, "html.parser")

    links: list[str] = []

    for a in soup.find_all("a"):
        classes = a.get("class", [])
        if not classes:
            continue

        # 只要 class 中含有以 "product-card_cardWrapper" 开头的字段，就认为是商品卡片
        if any(cls.startswith("product-card_cardWrapper") for cls in classes):
            href = a.get("href")
            if not href:
                continue

            # 处理相对链接 -> 绝对链接
            full_url = urljoin(DOMAIN, href)

            # 去掉 URL 中的 fragment（#intid=...）
            full_url, _ = urldefrag(full_url)

            links.append(full_url)

    return links


# ----------------------------------------------------------------------
# 主逻辑：按类目自动翻页抓取
# ----------------------------------------------------------------------

def collect_all_links(base_urls: list[str]) -> list[str]:
    all_links: set[str] = set()

    for base_url in base_urls:
        print(f"\n🟡 开始处理类目入口: {base_url}")

        page = 1
        empty_pages = 0
        last_page_links: set[str] | None = None

        while True:
            url = base_url.format(page)
            print(f"  -> 抓取第 {page} 页: {url}")

            html = fetch_page(url)
            if not html:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    break
                page += 1
                time.sleep(SLEEP_SECONDS)
                continue

            links = extract_product_links(html)
            current_set = set(links)

            if not links:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    break
            else:
                if last_page_links is not None and current_set == last_page_links:
                    break

                last_page_links = current_set
                new_links = [u for u in links if u not in all_links]
                all_links.update(new_links)

            page += 1
            time.sleep(SLEEP_SECONDS)

    all_links_list = sorted(all_links)
    print(f"\n✅ 抓到 {len(all_links_list)} 条去重后的商品链接")
    return all_links_list



def save_links(links: list[str], filepath: Path) -> None:
    """把链接列表按行写入到 txt 文件。"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", encoding="utf-8") as f:
        for url in links:
            f.write(url + "\n")
    print(f"💾 已写入到: {filepath.resolve()}")


def collect_jacket_links():
    links = collect_all_links(BASE_URLS_JACKET)
    save_links(links, OUTPUT_FILE_JACKET)

def collect_lingerie_links():
    links = collect_all_links(BASE_URLS_LINGERIE)
    save_links(links, OUTPUT_FILE_LINGERIE)



if __name__ == "__main__":
    collect_lingerie_links()
    collect_jacket_links()
