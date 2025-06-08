import requests
from bs4 import BeautifulSoup
import time
from pathlib import Path

# ======================
# 输入参数（可以自行修改）
# ======================
base_url = "https://www.camper.com/en_GB/women/shoes?sort=default&page={}"
total_pages = 30  # 总页数
output_file = "D:/TB/Products/camper/publication/product_urls.txt"
SAVE_FILE = Path(output_file)
delay_per_request = 1  # 每次请求延时（秒）
link_prefix = "https://www.camper.com"  # 补充链接前缀

SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
# ======================
# 爬取函数
# ======================
def get_links_from_page(url):
    SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败: {url}，错误信息: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # 选择所有商品的链接
    product_divs = soup.find_all("div", class_="ant-col grid-item overflow-hidden ant-col-xs-12 ant-col-md-8 ant-col-lg-6 ant-col-xl-6 ant-col-xxl-6")

    links = []
    for div in product_divs:
        a_tag = div.find("a", class_="block")
        if a_tag and a_tag.get("href"):
            href = a_tag["href"]
            # 如果是相对链接，加上前缀
            if href.startswith("/"):
                href = link_prefix + href
            links.append(href)

    return links

# ======================
# 主程序
# ======================
def main():
    all_links = []

    for page in range(1, total_pages + 1):
        url = base_url.format(page)
        print(f"正在抓取第 {page} 页: {url}")

        links = get_links_from_page(url)
        if links:
            print(f"找到 {len(links)} 个商品链接")
            all_links.extend(links)
        else:
            print(f"第 {page} 页未找到商品链接，跳过")

        time.sleep(delay_per_request)

    # 去重
    all_links = list(set(all_links))

    # 写入文件
    with open(output_file, "w", encoding="utf-8") as f:
        for link in all_links:
            f.write(link + "\n")

    print(f"\n✅ 全部完成！共获取 {len(all_links)} 个商品链接，已保存到 {output_file}")

# ======================
# 执行主程序
# ======================
if __name__ == "__main__":
    main()
