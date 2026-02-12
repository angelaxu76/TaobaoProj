import re
import time
import random
from pathlib import Path

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import BARBOUR
from common_taobao.core.selenium_utils import get_driver as get_shared_driver, quit_driver

# ✅ 两个入口：Barbour & Barbour International（第1页无参，其余 ?dcp=N）
BASE_URLS = [
    "https://www.houseoffraser.co.uk/brand/barbour",
    "https://www.houseoffraser.co.uk/brand/barbour-international",
]

OUTPUT_PATH = BARBOUR["LINKS_FILES"]["houseoffraser"]
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# 商品详情链接的通用特征：结尾/片段中带 -123456 这类数字 ID（不少还带 #colcode=）
PRODUCT_HREF_PATTERN = re.compile(r"-\d{5,}([/#?]|$)")

# 分页链接中的 dcp=N
DCP_IN_HREF = re.compile(r"[?&]dcp=(\d+)")


def get_driver():
    """
    使用 common_taobao.selenium_utils 提供的共享 driver，
    不再通过 undetected_chromedriver / driver_auto 联网下载。
    """
    return get_shared_driver(
        name="houseoffraser",
        headless=False,             # 你如果想静默可以自己改 True
        window_size="1920,1080",
    )


def _build_page_url(base_url: str, page: int) -> str:
    """HoF 分页：第1页无参，其余页使用 ?dcp=N"""
    if page <= 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}dcp={page}"


def _soft_scroll(driver, steps=5, pause=0.5):
    """多段滚动触发懒加载"""
    for i in range(steps):
        driver.execute_script(
            "window.scrollBy(0, Math.floor(document.body.scrollHeight * 0.30));"
        )
        time.sleep(pause)
    # 回到顶部，给 DOM 稳定时间
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.4)


def _wait_products(driver, timeout=15):
    """
    兼容等待策略：
    - 优先等待 .ProductImageList
    - 兜底等待可能的商品 a 元素
    """
    wait_css = ", ".join([
        "a.ProductImageList",
        "a[data-testid*='product']",
        "a[href*='-'][href*='/']",
    ])
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
        )
        return True
    except Exception:
        return False


def _discover_total_pages(html: str) -> int:
    """
    从第1页的分页区域抓取最大 dcp 值，作为总页数。
    找不到则返回一个保守上限（200）。
    """
    soup = BeautifulSoup(html, "html.parser")
    max_page = 1
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        m = DCP_IN_HREF.search(href)
        if m:
            try:
                n = int(m.group(1))
                if n > max_page:
                    max_page = n
            except ValueError:
                pass
    return max(max_page, 1)


def extract_links_from_html(html: str):
    """
    提取逻辑（保持原选择器优先 + 兜底）：
    1) 先走 a.ProductImageList（与你原逻辑一致）
    2) 若为空，再对所有 a[href] 用正则筛选含 -数字(≥5位) 的详情链接
    """
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    # 1) 原选择器
    for tag in soup.select("a.ProductImageList"):
        href = (tag.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("http"):
            links.add(href)
        elif href.startswith("/"):
            links.add("https://www.houseoffraser.co.uk" + href)

    if links:
        return links

    # 2) 兜底
    for tag in soup.select("a[href]"):
        href = (tag.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            full = "https://www.houseoffraser.co.uk" + href
        elif href.startswith("http"):
            full = href
        else:
            continue

        if PRODUCT_HREF_PATTERN.search(href):
            links.add(full)

    return links


def _crawl_category(driver, base_url: str, all_links: set):
    """
    核心策略：
    - 第1页：加载 -> 滚动 -> 等待 -> 提取链接 + 发现总页数
    - 之后页：逐页爬，连着 3 页“无新增”才停止（防抖）
    """
    # 第 1 页
    first_url = _build_page_url(base_url, 1)
    print(f"🌐 抓取第 1 页: {first_url}")
    driver.get(first_url)

    # 页面挂载 & 懒加载
    time.sleep(1.0)
    _soft_scroll(driver, steps=6, pause=0.45)
    _wait_products(driver, timeout=18)

    html = driver.page_source
    total_pages = _discover_total_pages(html)
    print(f"🔎 解析到总页数（可能）：{total_pages}")

    first_links = extract_links_from_html(html)
    new_links = [u for u in first_links if u not in all_links]
    print(f"✅ 第 1 页提取 {len(new_links)} 个新链接")
    all_links.update(new_links)

    # 后续页
    consecutive_no_new = 0
    for page in range(2, total_pages + 1):
        page_url = _build_page_url(base_url, page)
        print(f"🌐 抓取第 {page} 页: {page_url}")
        driver.get(page_url)

        # 给页面挂载时间 + 懒加载滚动
        time.sleep(0.8 + random.random() * 0.6)
        _soft_scroll(driver, steps=5, pause=0.4)
        _wait_products(driver, timeout=15)

        html = driver.page_source
        links = extract_links_from_html(html)
        page_new = [u for u in links if u not in all_links]

        if page_new:
            print(f"✅ 第 {page} 页提取 {len(page_new)} 个新链接")
            all_links.update(page_new)
            consecutive_no_new = 0
        else:
            consecutive_no_new += 1
            print(f"ℹ️ 第 {page} 页无新增链接（连续 {consecutive_no_new}/3）")

        # 连续 3 页没新增 → 结束该分类（防止偶发某页判空就提前退出）
        if consecutive_no_new >= 3:
            print("🛑 连续 3 页无新增，结束该分类")
            break

        # 页间随机等待，降低风控
        time.sleep(0.7 + random.random() * 0.8)


def houseoffraser_get_links():
    print("🚀 开始抓取 House of Fraser 商品链接（Barbour & Barbour International）")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    driver = get_driver()

    try:
        # ✅ 只在首次加载第一个分类前停留 10 秒手动点击 Cookie（后续复用同一实例）
        print("🕒 已打开浏览器，将打开首分类第1页。请在 10 秒内手动点击 Cookie 的 'Allow all' 按钮...")
        driver.get(BASE_URLS[0])
        time.sleep(10)
        print("✅ 已等待 10 秒，开始正式抓取")

        all_links = set()

        # ✅ 依次抓取两个分类（Barbour / Barbour International）
        for base_url in BASE_URLS:
            print(f"\n===== 🧭 当前分类：{base_url} =====")
            _crawl_category(driver, base_url, all_links)

        # ✅ 写入 txt（覆盖写）
        links_sorted = sorted(all_links)
        OUTPUT_PATH.write_text("\n".join(links_sorted), encoding="utf-8")

        print(f"\n✅ 抓取完成：共 {len(links_sorted)} 条链接")
        print(f"📝 已写入: {OUTPUT_PATH}")

    finally:
        quit_driver(driver)
