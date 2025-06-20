import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CLARKS, ensure_all_dirs

# === 配置 ===
PRODUCT_LINKS_FILE = CLARKS["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = CLARKS["IMAGE_DIR"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_WORKERS = 5
SKIP_EXISTING_IMAGE = True

ensure_all_dirs(IMAGE_DIR)

UK_TO_EU_CM = {
    "3": ("35.5", "22.1"), "3.5": ("36", "22.5"), "4": ("37", "22.9"),
    "4.5": ("37.5", "23.3"), "5": ("38", "23.7"), "5.5": ("39", "24.1"),
    "6": ("39.5", "24.5"), "6.5": ("40", "25"), "7": ("41", "25.4"),
    "7.5": ("41.5", "25.7"), "8": ("42", "26"), "8.5": ("42.5", "26.5"),
    "9": ("43", "27"), "9.5": ("44", "27.5"), "10": ("44.5", "28"),
    "10.5": ("45", "28.5"), "11": ("46", "28.9"), "11.5": ("46.5", "29.3"), "12": ("47", "30")
}

def extract_product_code(url):
    match = re.search(r'/([0-9]+)-p', url)
    return match.group(1) if match else "unknown"

def extract_image_urls(soup):
    image_urls = []
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag:
        try:
            json_data = json.loads(script_tag.string)
            image_urls = json_data.get("props", {}).get("pageProps", {}).get("product", {}).get("imageUrls", [])
        except Exception as e:
            print(f"⚠️ 图片 JSON 提取失败: {e}")
    return image_urls

def download_image(url, save_path):
    try:
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 已存在，跳过: {save_path.name}")
            return
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            print(f"🖼️ 下载成功: {save_path.name}")
        else:
            print(f"⚠️ 图片请求失败（{r.status_code}）: {url}")
    except Exception as e:
        print(f"❌ 下载失败: {url} → {e}")

def process_image_only(url):
    print(f"📷 处理图片: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        code = extract_product_code(url)
        image_urls = extract_image_urls(soup)

        for idx, img_url in enumerate(image_urls):
            img_path = IMAGE_DIR / f"{code}_{idx + 1}.jpg"
            download_image(img_url, img_path)
    except Exception as e:
        print(f"❌ 图片处理失败: {url} → {e}")

def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 链接文件不存在: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"📦 共 {len(urls)} 个商品图片待处理")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_only, url) for url in urls]
        for future in as_completed(futures):
            future.result()

    print("\n✅ 所有图片下载完成")

if __name__ == "__main__":
    main()
