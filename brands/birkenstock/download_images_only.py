import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import BIRKENSTOCK, ensure_all_dirs

# === 配置 ===
PRODUCT_LINKS_FILE = BIRKENSTOCK["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = BIRKENSTOCK["IMAGE_DOWNLOAD"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_WORKERS = 5
SKIP_EXISTING_IMAGE = True

ensure_all_dirs(IMAGE_DIR)

def extract_product_code_from_img_url(url):
    url_clean = re.sub(r"\?.*$", "", url)
    match = re.search(r"/(\d{5,7})/", url_clean)
    return match.group(1) if match else "unknown"

def extract_image_urls(soup):
    return [img.get("data-img") for img in soup.find_all("img", class_="zoom-icon") if img.get("data-img")]

def download_image(img_url, product_code, index):
    product_code = product_code.zfill(7)  # ✅ 编码补0到7位
    filename = f"{product_code}_{index + 1}.jpg"
    save_path = IMAGE_DIR / filename
    try:
        if SKIP_EXISTING_IMAGE and save_path.exists():
            print(f"✅ 已存在，跳过: {filename}")
            return
        r = requests.get(img_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            print(f"🖼️ 下载成功: {filename}")
        else:
            print(f"⚠️ 请求失败（{r.status_code}）: {img_url}")
    except Exception as e:
        print(f"❌ 下载失败: {img_url} → {e}")

def process_image_only(url):
    print(f"📷 处理商品页面: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        img_urls = extract_image_urls(soup)
        if not img_urls:
            print("⚠️ 未找到图片链接")
            return
        product_code = extract_product_code_from_img_url(img_urls[0])
        for idx, img_url in enumerate(img_urls):
            download_image(img_url, product_code, idx)
    except Exception as e:
        print(f"❌ 页面处理失败: {url} → {e}")

def main():
    if not PRODUCT_LINKS_FILE.exists():
        print(f"❌ 链接文件不存在: {PRODUCT_LINKS_FILE}")
        return
    urls = [u.strip() for u in PRODUCT_LINKS_FILE.read_text(encoding="utf-8").splitlines() if u.strip()]
    print(f"📦 共 {len(urls)} 个商品待下载图片")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_image_only, url) for url in urls]
        for future in as_completed(futures):
            future.result()

    print("\n✅ 所有图片下载完成")

if __name__ == "__main__":
    main()
