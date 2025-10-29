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

sys.stdout.reconfigure(encoding='utf-8')

# ========= 参数配置 =========
LINKS_FILE = CAMPER["LINKS_FILE"]
WAIT = 1.0                      # 每页抓取间隔（秒）
MAX_EMPTY_PAGES = 3             # 连续多少页无数据就换类目
LINK_PREFIX = "https://www.camper.com"

# ✅ 类目入口（注意每一行末尾都有逗号！）
BASE_URLS = [
    # 汇总页
    "https://www.camper.com/en_GB/women/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes?sort=default&page={}",
    "https://www.camper.com/en_GB/kids/shoes?sort=default&page={}",

    # LAB/ALL 系列
    "https://www.camper.com/en_GB/women/shoes/all_shoes_lab_women?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/all_shoes_lab_men?filter.collection=allabm&sort=default&page={}",

    # 新品
    "https://www.camper.com/en_GB/men/shoes/new_collection?filter.collection=neco&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/new_collection?filter.collection=neco&sort=default&page={}",

    # 女款细分
    "https://www.camper.com/en_GB/women/shoes/ballerinas?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/sneakers?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/formal_shoes?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/casual?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/ankle_boots?filter.collection=allabw&sort=default&page={}",
    "https://www.camper.com/en_GB/women/shoes/boots?filter.collection=allabw&sort=default&page={}",

    # 男款细分
    "https://www.camper.com/en_GB/men/shoes/sneakers?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/formal_shoes?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/casual?filter.collection=allabm&sort=default&page={}",
    "https://www.camper.com/en_GB/men/shoes/ankle_boots?filter.collection=allabm&sort=default&page={}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

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

    # 选择器 1：兼容当前网格卡片（你现有脚本使用的 class）
    for a_tag in soup.select("div.grid-item a.block[href]"):
        if a_tag and a_tag.get("href"):
            href = a_tag["href"].strip()
            if href.startswith("/"):
                href = LINK_PREFIX + href
            links.add(href)

    # 选择器 2：兜底，抓取所有商品卡片上的 <a>（避免 UI 细微变动时丢失）
    if not links:
        for a in soup.select("a[href*='//www.camper.com/en_']"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if ("/women/shoes/" in href or "/men/shoes/" in href or "/kids/shoes/" in href):
                # 详情页层级更深，粗略过滤掉列表/筛选页
                if href.count("/") >= 7:
                    if href.startswith("/"):
                        href = LINK_PREFIX + href
                    links.add(href)

    return list(links)

# ========= 主流程：自动翻页，连续空页阈值后切类目 =========
def camper_get_links():
    all_links = set()

    for base_url in BASE_URLS:
        empty_pages = 0
        page = 1
        print(f"\n▶️ 入口：{base_url}")
        while True:
            url = base_url.format(page)
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
                page += 1
            else:
                print(f"⚠️ 第 {page} 页无链接或抓取失败")
                empty_pages += 1
                page += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    print(f"⏹️ 连续 {MAX_EMPTY_PAGES} 页为空，切换下一个入口")
                    break
            time.sleep(WAIT)

    # 输出
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共抓取链接: {len(all_links)}，已保存到: {LINKS_FILE}")

if __name__ == "__main__":
    camper_get_links()
