# -*- coding: utf-8 -*-
"""
Camper 商品链接抓取（增强版）
变化点：
1）自动翻页：从第 1 页开始，只要能抓到商品就继续；连续 3 页为空就切到下一个类别。
2）更健壮的选择器：兼容多个卡片结构，尽量从 <a> 提取链接。
3）修复 BASE_URLS 少逗号导致的 format IndexError。
4）抓到的链接去重、排序后落盘。
"""
import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path
from config import CAMPER  # ✅ 根据品牌切换
import sys
import re
sys.stdout.reconfigure(encoding='utf-8')

# ========= 参数配置 =========
LINKS_FILE = CAMPER["LINKS_FILE"]
WAIT = 1.0                      # 每页抓取间隔（秒）
MAX_EMPTY_PAGES = 3             # 连续多少页无数据就换类目
LINK_PREFIX = "https://www.camper.com"

# ✅ 类目入口（注意每一行末尾都有逗号！）
BASE_URLS = [
    # 汇总页
    "https://www.camper.com/en_GB/men/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/kids/shoes?sort=default&page={}",


    "https://www.camper.com/en_GB/women/shoes/casual?filter.typology=_CST_T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/ballerinas?filter.typology=_CST_T10&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/boots?filter.typology=T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/loafers?filter.typology=_CST_T17&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/sneakers?filter.typology=_CST_T04&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/heels?filter.typology=_CST_T07&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/casual?filter.typology=_CST_T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/formal_shoes?filter.typology=_CST_T05&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/fall_winter?filter.collection=fw&sort=default&page={}",
    "https://www.camperlab.com/en_GB/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/fall_winter?filter.collection=fw&sort=default&page={}",
    "https://www.camperlab.com/en_GB/men/shoes/all_shoes_lab_men?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/fall_winter?filter.collection=fw&sort=default&page={}",
    
    "https://www.camper.com/en_GB/men/shoes/ankle_boots?filter.typology=_CST_T09&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/sneakers?filter.typology=_CST_T04&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/formal_shoes?filter.typology=_CST_T05&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/casual?filter.typology=_CST_T01&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/loafers?page={}",
    

    # LAB/ALL 系列
    "https://www.camper.com/en_GB/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/all_shoes_lab_men?filter.collection=allabm&sort=default&page={}",

    # # 新品
    # "https://www.camper.com/en_GB/men/shoes/new_collection?filter.collection=neco&sort=default&page={}",
    # "https://www.camper.com/en_GB/women/shoes/new_collection?filter.collection=neco&sort=default&page={}",

    # 女款细分
    "https://www.camper.com/en_GB/women/shoes/ballerinas?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/sneakers?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/formal_shoes?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/casual?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/ankle_boots?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/boots?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/heels?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/loafers?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/fall_winter?filter.collection=allabw&sort=default&page={}",

    # 男款细分
    "https://www.camper.com/en_GB/men/shoes/sneakers?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/formal_shoes?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/casual?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/ankle_boots?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/loafers?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/fall_winter?filter.collection=allabw&sort=default&page={}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}


def normalize_link(href: str) -> str:
    """
    把商品链接规范化：
    - 补全域名
    - 去掉 ? 后面的所有参数（包括 size、utm 等）
    - 去掉末尾多余的 /
    """
    href = (href or "").strip()
    if not href:
        return ""

    # 相对路径转绝对
    if href.startswith("/"):
        href = LINK_PREFIX + href

    # 去掉 URL 参数（?size=41 之类）
    href = href.split("?", 1)[0]

    # 可选：去掉末尾斜杠，避免 ...001 和 ...001/ 算两条
    href = href.rstrip("/")

    return href


def parse_pagination_spec(url: str):
    """
    解析 URL 中的 page 占位符:
    - page={}        -> (base_url, start=1, end=None)   自动模式
    - page={20}      -> (base_url, start=1, end=20)     1..20
    - page={3-12}    -> (base_url, start=3, end=12)     3..12
    解析后把 {...} 统一替换回 {} 供 format 使用
    """
    m = re.search(r"page=\{(\d+)(?:-(\d+))?\}", url)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else int(m.group(1))
        base_url = re.sub(r"\{(\d+)(?:-(\d+))?\}", "{}", url)
        return base_url, start, end
    else:
        # 没写数字范围，保持原样作为自动模式
        return url, 1, None


# ========= 带重试的请求 =========
def fetch_with_retry(url, retries=3, timeout=20):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"❌ 第 {attempt} 次请求失败: {url}，错误: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return None

# ========= 解析页面提取链接 =========
def get_links_from_page(url):
    html = fetch_with_retry(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    links = set()

    # 选择器 1
    for a_tag in soup.select("div.grid-item a.block[href]"):
        href = normalize_link(a_tag.get("href"))
        if href:
            links.add(href)

    # 选择器 2
    for a in soup.select("a[href*='//www.camper.com/en_']"):
        href = normalize_link(a.get("href"))
        if not href:
            continue
        if ("/women/shoes/" in href or "/men/shoes/" in href or "/kids/shoes/" in href):
            if href.count("/") >= 7:
                links.add(href)

    return list(links)

# ========= 主流程：自动翻页，连续空页阈值后切类目 =========
def camper_get_links():
    all_links = set()

    for spec in BASE_URLS:
        # 关键：先解析 {N} / {A-B} / {} 这三种写法
        base_url, start, end = parse_pagination_spec(spec)

        empty_pages = 0
        page = start
        print(f"\n▶️ 入口：{base_url}（页数范围: {start} → {end or 'auto'}）")
        while True:
            url = base_url.format(page)  # 现在 base_url 已是标准 ...page={}
            print(f"🌐 抓取: {url}")
            links = get_links_from_page(url)

            if links:
                print(f"✅ 第 {page} 页: {len(links)} 条链接")
                before = len(all_links)
                all_links.update(links)
                added = len(all_links) - before
                if added > 0:
                    print(f"   ↳ 新增 {added} 条（去重后累计 {len(all_links)}）")
                empty_pages = 0
            else:
                print(f"⚠️ 第 {page} 页无链接或抓取失败")
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES and end is None:
                    print(f"⏹️ 连续 {MAX_EMPTY_PAGES} 页为空，切换下一个入口")
                    break

            # 若手动设了页数上限，到达就换入口
            if end is not None and page >= end:
                print(f"⏹️ 达到手动设定页数 {end}，切换下一个入口")
                break

            page += 1
            time.sleep(WAIT)

    # 输出
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共抓取链接: {len(all_links)}，已保存到: {LINKS_FILE}")

if __name__ == "__main__":
    camper_get_links()
