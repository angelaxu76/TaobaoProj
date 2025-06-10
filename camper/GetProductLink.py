import os
import re
import time
import requests
from bs4 import BeautifulSoup

# ========================
# ✅ 配置参数
# ========================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

output_file = r"D:\TB\Products\camper\publication\product_urls.txt"
delay_per_request = 1.0  # 请求间隔（秒）

# 多个性别分类的 URL 配置
gender_urls = {
    "men": ("https://www.camper.com/en_GB/men/shoes?sort=default&page={}", 20),
    "women": ("https://www.camper.com/en_GB/women/shoes?sort=default&page={}", 20)
}

# ========================
# ✅ 获取商品链接函数
# ========================
def get_links_from_page(url):
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for div in soup.find_all("div", class_=re.compile(r"ant-col grid-item")):
            a_tag = div.find("a", href=True)
            if a_tag:
                href = a_tag["href"].split("?")[0]
                if href.startswith("/en_GB"):
                    full_url = "https://www.camper.com" + href
                    links.append(full_url)
        return links
    except Exception as e:
        print(f"❌ 抓取失败: {url}，错误: {e}")
        return []

# ========================
# ✅ 主程序入口
# ========================
def main():
    all_links = []

    for gender, (base_url, total_pages) in gender_urls.items():
        print(f"\n🟢 开始抓取 {gender} 分类链接...")
        for page in range(1, total_pages + 1):
            url = base_url.format(page)
            links = get_links_from_page(url)
            print(f"  第 {page} 页抓取 {len(links)} 条")
            all_links.extend(links)
            time.sleep(delay_per_request)

    all_links = sorted(set(all_links))
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for link in all_links:
            f.write(link + "\n")

    print(f"\n✅ 所有分类共抓取 {len(all_links)} 个商品链接，保存到: {output_file}")

if __name__ == "__main__":
    main()
