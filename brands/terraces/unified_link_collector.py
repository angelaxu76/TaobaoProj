import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path
import sys
from urllib.parse import urljoin
from config import TERRACES  # ✅ 使用 config 中的 TERRACES 配置

sys.stdout.reconfigure(encoding='utf-8')

# ========= 参数配置 =========
LINKS_FILE = TERRACES["LINKS_FILE"]
BASE_URL = "https://www.terracesmenswear.co.uk/barbour&page={}"
BASE_DOMAIN = "https://www.terracesmenswear.co.uk"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# ========= 带重试请求 =========
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

# ========= 获取商品链接 =========
def get_links_from_page(url):
    html = fetch_with_retry(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    product_titles = soup.find_all("h4", class_="product__title")

    links = []
    for h4 in product_titles:
        a_tag = h4.find("a")
        if a_tag and a_tag.get("href"):
            href = a_tag["href"].strip()
            full_url = urljoin(BASE_DOMAIN, href)  # ✅ 转换为完整链接
            links.append(full_url)

    return links

# ========= 主逻辑函数（可供 pipeline 调用） =========
def collect_terraces_links(max_pages=50, wait=1, max_empty_pages=3, output_file=LINKS_FILE):
    all_links = set()
    empty_pages = 0

    for page in range(1, max_pages + 1):
        url = BASE_URL.format(page)
        print(f"\n🌐 抓取: {url}")
        links = get_links_from_page(url)

        if links:
            print(f"✅ 第 {page} 页: {len(links)} 条链接")
            all_links.update(links)
            empty_pages = 0
        else:
            print(f"⚠️ 第 {page} 页无链接")
            empty_pages += 1
            if empty_pages >= max_empty_pages:
                print(f"⏹️ 连续 {max_empty_pages} 页为空，提前结束")
                break
        time.sleep(wait)

    # ✅ 确保目录存在并删除旧文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    with open(output_file, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\n🎉 共抓取链接: {len(all_links)}，已保存到: {output_file}")
    return len(all_links)

# ========= 脚本独立运行入口 =========
if __name__ == "__main__":
    collect_terraces_links()
