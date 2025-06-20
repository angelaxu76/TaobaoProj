
import os
import re
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from config import CLARKS

LINK_FILE = CLARKS["BASE"] / "publication" / "product_links.txt"
IMAGE_DIR = CLARKS["IMAGE_DIR"]
HEADERS = {"User-Agent": "Mozilla/5.0"}

def extract_product_code(url):
    match = re.search(r'/(\d+)-p', url)
    return match.group(1) if match else "unknown"

def download_image(url, save_path):
    if save_path.exists():
        print(f"🟡 已存在，跳过下载：{save_path.name}")
        return
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(r.content)
            print(f"📥 下载成功：{save_path.name}")
        else:
            print(f"⚠️ 状态码 {r.status_code}：{url}")
    except Exception as e:
        print(f"❌ 下载失败: {url}，原因：{e}")

def fetch_images(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        product_code = extract_product_code(url)
        script_tag = soup.find("script", id="__NEXT_DATA__")
        image_urls = []
        if script_tag:
            data = json.loads(script_tag.string)
            image_urls = data.get("props", {}).get("pageProps", {}).get("product", {}).get("imageUrls", [])

        for idx, img_url in enumerate(image_urls):
            img_path = IMAGE_DIR / f"{product_code}_{idx + 1}.jpg"
            download_image(img_url, img_path)

        print(f"✅ 图片完成：{product_code}")
    except Exception as e:
        print(f"❌ 图片失败：{url}，错误：{e}")

def main():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not LINK_FILE.exists():
        print(f"❌ 链接文件不存在：{LINK_FILE}")
        return
    with open(LINK_FILE, "r", encoding="utf-8") as f:
        links = [line.strip() for line in f if line.strip()]
    for url in links:
        fetch_images(url)

if __name__ == "__main__":
    main()
