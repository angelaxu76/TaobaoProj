
import os
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from config import BARBOUR

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
}

def extract_code_and_name(url: str):
    # 例如：https://www.barbour.com/gb/zola-quilted-jacket-LQU1822CR11.html
    filename = os.path.basename(urlparse(url).path)  # zola-quilted-jacket-LQU1822CR11.html
    if filename.endswith(".html"):
        filename = filename[:-5]
    parts = filename.split("-")
    code = parts[-1]
    name = "-".join(parts[:-1])
    return code, name

def extract_image_urls(page_content: str):
    soup = BeautifulSoup(page_content, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")
    if not script_tag:
        return []

    try:
        data = json.loads(script_tag.string.strip())
        images = data.get("image", [])
        if isinstance(images, list):
            return images
    except Exception as e:
        print(f"[解析失败] JSON 错误: {e}")
    return []

def download_barbour_images():
    links_file = BARBOUR["LINKS_FILE"]
    image_folder = BARBOUR["IMAGE_DOWNLOAD"]
    os.makedirs(image_folder, exist_ok=True)

    with open(links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"📦 共 {len(urls)} 个商品链接，开始依次下载...")

    for idx, url in enumerate(urls, 1):
        try:
            code, name = extract_code_and_name(url)
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            image_urls = extract_image_urls(resp.text)

            for i, img_url in enumerate(image_urls, 1):
                img_name = f"{code}-{name}_{i}.jpg"
                save_path = os.path.join(image_folder, img_name)
                img_data = requests.get(img_url, headers=headers, timeout=15).content
                with open(save_path, "wb") as f:
                    f.write(img_data)
                print(f"✅ [{idx}/{len(urls)}] 已保存: {img_name}")
        except Exception as e:
            print(f"❌ [{idx}/{len(urls)}] 失败: {url}，错误: {e}")

    print("🎯 所有图片处理完毕。")

if __name__ == "__main__":
    download_barbour_images()
