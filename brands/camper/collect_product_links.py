# -*- coding: utf-8 -*-
"""
Camper 商品链接抓取（增强版 - 修复无限翻页）
修复点（针对你现在“每页固定 8 条，永远不空，停不下来”的问题）：
1）新增停止条件：连续 NO_NEW_LIMIT 页“无新增链接” -> 切换下一个入口
2）新增停止条件：页面签名重复 PAGE_REPEAT_LIMIT 次 -> 切换下一个入口
3）仍保留原逻辑：连续 MAX_EMPTY_PAGES 页为空 -> 切换下一个入口
4）抓到的链接全局去重后落盘
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
MAX_EMPTY_PAGES = 3             # 连续多少页无数据就换类目（保留原逻辑）
LINK_PREFIX = "https://www.camper.com"

# ✅ 新增：连续无新增页数限制（解决“每页都有8条但都是重复/推荐位”）
NO_NEW_LIMIT = 2                # 连续 2 页无新增 -> 停止该入口（你想更保守可改 3）

# ✅ 新增：页面内容重复限制（同一批链接反复出现）
PAGE_REPEAT_LIMIT = 1           # 页面签名重复 1 次即认为卡死（可改 2 更宽松）

# ✅ 类目入口（注意每一行末尾都有逗号！）
BASE_URLS = [
    # 汇总页
    "https://www.camper.com/en_GB/men/shoes?sort=default&page={}",

    "https://www.camper.com/en_GB/women/shoes/casual?filter.typology=_CST_T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/ballerinas?filter.typology=_CST_T10&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/boots?filter.typology=T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/loafers?filter.typology=_CST_T17&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/sneakers?filter.typology=_CST_T04&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/heels?filter.typology=_CST_T07&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/casual?filter.typology=_CST_T01&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/formal_shoes?filter.typology=_CST_T05&sort=default&page={}",
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

    if href.startswith("/"):
        href = LINK_PREFIX + href

    href = href.split("?", 1)[0]
    href = href.rstrip("/")
    return href


def parse_pagination_spec(url: str):
    """
    解析 URL 中的 page 占位符:
    - page={}        -> (base_url, start=1, end=None)   自动模式
    - page={20}      -> (base_url, start=1, end=20)     1..20
    - page={3-12}    -> (base_url, start=3, end=12)     3..12
    """
    m = re.search(r"page=\{(\d+)(?:-(\d+))?\}", url)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else int(m.group(1))
        base_url = re.sub(r"\{(\d+)(?:-(\d+))?\}", "{}", url)
        return base_url, start, end
    else:
        return url, 1, None


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


def _page_signature(links):
    """把本页链接做成稳定签名，用于检测重复页面内容"""
    uniq = sorted(set([normalize_link(x) for x in links if x]))
    return "|".join(uniq)


def camper_get_links():
    all_links = set()

    for spec in BASE_URLS:
        base_url, start, end = parse_pagination_spec(spec)

        empty_pages = 0
        consecutive_no_new = 0
        page_repeat_count = 0

        seen_page_sigs = set()

        page = start
        print(f"\n▶️ 入口：{base_url}（页数范围: {start} → {end or 'auto'}）")

        while True:
            url = base_url.format(page)
            print(f"🌐 抓取: {url}")
            links = get_links_from_page(url)

            # ---- 新增：页面签名重复检测（解决：每页都有 8 条但其实是同一批）----
            sig = _page_signature(links)
            if sig and sig in seen_page_sigs:
                page_repeat_count += 1
                print(f"⚠️ 第 {page} 页页面内容重复（重复计数 {page_repeat_count}/{PAGE_REPEAT_LIMIT}）")
                if page_repeat_count >= PAGE_REPEAT_LIMIT and end is None:
                    print("⏹️ 页面内容重复，判定进入兜底/推荐循环页，切换下一个入口")
                    break
            else:
                if sig:
                    seen_page_sigs.add(sig)
                page_repeat_count = 0

            if links:
                print(f"✅ 第 {page} 页: {len(links)} 条链接")
                before = len(all_links)
                all_links.update(links)
                added = len(all_links) - before

                if added > 0:
                    print(f"   ↳ 新增 {added} 条（去重后累计 {len(all_links)}）")
                    consecutive_no_new = 0
                else:
                    consecutive_no_new += 1
                    print(f"   ↳ 本页无新增（连续 {consecutive_no_new}/{NO_NEW_LIMIT}）")
                    if consecutive_no_new >= NO_NEW_LIMIT and end is None:
                        print(f"⏹️ 连续 {NO_NEW_LIMIT} 页无新增链接，切换下一个入口")
                        break

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
